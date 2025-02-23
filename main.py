from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging
from pythonjsonlogger import jsonlogger
import uvicorn
import re
import os
import random
from typing import Optional, List, Callable, TypeVar, Any
import openai
from dotenv import load_dotenv
import aioredis
import json
from prometheus_fastapi_instrumentator import Instrumentator
import hashlib
from datetime import timedelta, datetime
import time
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
    RetryCallState,
    after_log
)
from storage import PromptStorage, RedisPromptStorage
from models import PromptRequest, PromptResponse, DomainType, ExpertiseLevel, OutputFormat

# Load environment variables
load_dotenv()

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")

# Configure Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

# Configure JSON logging
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

class RateLimiter:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.rate_limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        self.window_size = 60  # 1 minute window

    async def is_rate_limited(self, key: str) -> bool:
        current = int(time.time())
        window_key = f"ratelimit:{key}:{current // self.window_size}"
        
        # Get the current count and increment it atomically
        count = await self.redis.incr(window_key)
        
        if count == 1:
            # Set expiration for new keys
            await self.redis.expire(window_key, self.window_size)
        
        return count > self.rate_limit

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, redis_client: aioredis.Redis):
        super().__init__(app)
        self.limiter = RateLimiter(redis_client)

    async def dispatch(self, request: Request, call_next: Callable):
        # Extract client identifier (IP address or API key)
        client_id = request.headers.get("X-API-Key") or request.client.host
        
        # Check rate limit
        if await self.limiter.is_rate_limited(client_id):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": self.limiter.rate_limit,
                    "window_size": self.limiter.window_size,
                    "unit": "requests per minute"
                }
            )
        
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.limiter.rate_limit)
        response.headers["X-RateLimit-Window-Seconds"] = str(self.limiter.window_size)
        
        return response

app = FastAPI(
    title="Smart Prompt API",
    description="API for refining 'lazy' prompts into high-quality prompts using AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Prometheus metrics after CORS
Instrumentator().instrument(app).expose(app)

# Redis connection pool
redis = None

# Global storage instance
prompt_storage = None

@app.on_event("startup")
async def startup_event():
    global redis, prompt_storage
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    prompt_storage = RedisPromptStorage(redis)
    # Clear cache on startup (useful for testing)
    if os.getenv("ENVIRONMENT") == "test":
        await prompt_storage.clear_cache()
    # Add rate limiting middleware after Redis is initialized
    app.add_middleware(RateLimitMiddleware, redis_client=redis)

@app.on_event("shutdown")
async def shutdown_event():
    if redis:
        await redis.close()

def generate_cache_key(request: PromptRequest) -> str:
    """Generate a unique cache key for a prompt request."""
    key_data = {
        "lazy_prompt": request.lazy_prompt.strip().lower(),  # Normalize the prompt
        "domain": request.domain,
        "expertise_level": request.expertise_level,
        "output_format": request.output_format,
        "include_best_practices": request.include_best_practices,
        "include_examples": request.include_examples
    }
    key_string = json.dumps(key_data, sort_keys=True)
    return f"prompt:{hashlib.sha256(key_string.encode()).hexdigest()}"

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        if redis:
            await redis.ping()
            redis_status = "connected"
        else:
            redis_status = "disconnected"
            
        return {
            "status": "healthy",
            "redis": redis_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "error": str(e)}
        )

def get_wait_time_from_error(error: Exception) -> float:
    """Extract wait time from OpenAI's rate limit response."""
    if isinstance(error, openai.RateLimitError):
        error_message = str(error)
        match = re.search(r"Please try again in (\d+\.?\d*)s", error_message)
        if match:
            return float(match.group(1))
    return 4.0  # Default minimum wait time

def dynamic_wait(retry_state: RetryCallState) -> float:
    """Dynamic wait strategy that uses the wait time from OpenAI's response."""
    error = retry_state.outcome.exception()
    base_wait = get_wait_time_from_error(error)
    
    # Add some jitter to prevent thundering herd
    jitter = random.uniform(0, 1)
    wait_time = base_wait * (1 + jitter * 0.1)  # Add up to 10% jitter
    
    # Cap maximum wait time at 60 seconds
    return min(wait_time, 60.0)

# Configure OpenAI retries
logger = logging.getLogger()
T = TypeVar("T")

@retry(
    retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)),
    wait=wait_exponential(multiplier=1),  # Base wait, will be overridden by dynamic wait time
    stop=stop_after_attempt(5),  # Maximum 5 attempts
    before_sleep=lambda retry_state: dynamic_wait(retry_state),  # Use our custom wait strategy
)
async def retry_openai_call(func: Callable[..., T], *args, **kwargs) -> T:
    """Wrapper for OpenAI API calls with dynamic backoff retry logic."""
    try:
        return await func(*args, **kwargs)
    except RetryError as e:
        logger.error(f"Max retries reached for OpenAI API call: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable due to rate limiting. Please try again later."
        )
    except Exception as e:
        logger.error(f"Unexpected error in OpenAI API call: {str(e)}")
        raise

async def detect_topics(prompt: str) -> List[str]:
    """Use OpenAI to detect key technical topics in the prompt."""
    try:
        client = openai.AsyncClient()
        response = await retry_openai_call(
            client.chat.completions.create,
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a technical topic analyzer. Extract key technical topics from the given text."},
                {"role": "user", "content": f"Extract 3-5 key technical topics from this prompt: {prompt}"}
            ],
            max_tokens=100,
            temperature=0.3
        )
        topics = response.choices[0].message.content.strip().split("\n")
        return [topic.strip("- ") for topic in topics if topic.strip()]
    except Exception as e:
        logger.error(f"Error detecting topics: {str(e)}")
        return []

async def generate_topic_details(topics: List[str], domain: str, expertise_level: str) -> dict:
    """Generate detailed information about each detected topic using OpenAI."""
    try:
        client = openai.AsyncClient()
        details = {}
        
        for topic in topics:
            response = await retry_openai_call(
                client.chat.completions.create,
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a technical documentation expert who creates detailed topic overviews."},
                    {"role": "user", "content": f"Create a detailed overview of '{topic}' for {expertise_level} level technologists in the {domain} domain. Include key concepts, best practices, and common challenges."}
                ],
                max_tokens=500,
                temperature=0.7
            )
            details[topic] = response.choices[0].message.content.strip()
            # Add a small delay between requests to help prevent rate limiting
            await asyncio.sleep(0.5)
        
        return details
    except Exception as e:
        logger.error(f"Error generating topic details: {str(e)}")
        return {}

async def generate_prompt_file(request: PromptRequest, topics: List[str], topic_details: dict, refs: Optional[List[str]]) -> str:
    """Generate a complete prompt file in markdown format."""
    try:
        client = openai.AsyncClient()
        
        content = f"""# {request.lazy_prompt.capitalize()}

## Overview
This prompt provides guidance for {request.lazy_prompt} in the context of {request.domain} domain, targeted at {request.expertise_level} level technologists.

## Key Topics
"""
        
        for topic in topics:
            content += f"\n### {topic}\n"
            if topic in topic_details:
                content += f"{topic_details[topic]}\n"

        if refs:
            content += "\n## Recommended References\n"
            for ref in refs:
                content += f"- {ref}\n"

        # Get additional sections from OpenAI with retry
        response = await retry_openai_call(
            client.chat.completions.create,
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a technical documentation expert who creates comprehensive prompt files."},
                {"role": "user", "content": f"Based on this content, generate additional sections for Implementation Guidelines, Best Practices, and Common Pitfalls for {request.lazy_prompt}:\n\n{content}"}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        
        content += "\n" + response.choices[0].message.content.strip()
        return content
    except Exception as e:
        logger.error(f"Error generating prompt file: {str(e)}")
        return ""

async def enhance_prompt(request: PromptRequest) -> PromptResponse:
    """
    Transform a lazy prompt into a sophisticated one using OpenAI,
    incorporating domain expertise, best practices, and proper structure.
    """
    # First check if we're in a test environment
    is_test = os.getenv("ENVIRONMENT") == "test"
    
    # Check cache only if not in test environment or if explicitly testing caching
    cache_key = generate_cache_key(request)
    cached_response = None
    if not is_test or "test_cache" in str(request.lazy_prompt):
        cached_response = await redis.get(cache_key)
    
    if cached_response:
        response_data = json.loads(cached_response)
        return PromptResponse(**response_data, cached=True)
        
    try:
        client = openai.AsyncClient()
        # Detect technical topics first
        topics = await detect_topics(request.lazy_prompt)
        
        # Check for related prompts that might help inform this one
        related_prompts = await prompt_storage.search_related(topics, str(request.domain))
        
        # If we found related prompts, include their insights in the system message
        additional_context = ""
        if related_prompts:
            additional_context = "\nConsider these related insights:\n"
            for p in related_prompts:
                additional_context += f"- {p['response']['refined_prompt'][:200]}...\n"
        
        # Generate detailed information about each topic
        topic_details = await generate_topic_details(topics, str(request.domain), str(request.expertise_level))
        
        # Build the system prompt based on request parameters
        system_prompts = {
            "architecture": "You are an experienced Systems Architect with deep knowledge of software architecture patterns, scalability, and enterprise systems.",
            "development": "You are a Senior Software Developer with expertise in clean code, design patterns, and software engineering best practices.",
            "infrastructure": "You are a DevOps Engineer and Cloud Architect with extensive experience in cloud infrastructure, CI/CD, and infrastructure as code.",
            "security": "You are a Security Architect with deep knowledge of security patterns, threat modeling, and secure system design.",
            "general": "You are a Technology Expert with broad knowledge across software development, architecture, and infrastructure."
        }
        format_templates = {
            "simple": "Provide a clear and concise response.",
            "detailed": "Provide a comprehensive response with sections for overview, details, considerations, and next steps.",
            "tutorial": "Structure the response as a step-by-step tutorial with examples and explanations.",
            "checklist": "Present the response as a detailed checklist of items to consider or implement."
        }

        # Build the enhanced prompt
        content_parts = [
            f"Enhance and respond to this prompt: {request.lazy_prompt}",
            f"Format: {format_templates[request.output_format]}"
        ]
        if request.include_best_practices:
            content_parts.append("Include relevant industry best practices and standards.")
        if request.include_examples:
            content_parts.append("Provide specific technical examples where appropriate.")
        
        messages = [
            {"role": "system", "content": f"{system_prompts[request.domain]}\n\nRespond as if explaining to a {request.expertise_level} level technologist.{additional_context}"},
            {"role": "user", "content": "\n".join(content_parts)}
        ]
        
        # Make OpenAI call with retry
        response = await retry_openai_call(
            client.chat.completions.create,
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        refined = response.choices[0].message.content.strip()

        # Get recommended references if best practices are requested
        recommended_refs = []
        if request.include_best_practices:
            refs_response = await retry_openai_call(
                client.chat.completions.create,
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a technical documentation expert. Suggest relevant technical documentation, standards, or best practice guides."},
                    {"role": "user", "content": f"Suggest 2-3 technical references or documentation relevant to: {request.lazy_prompt}"}
                ],
                max_tokens=150,
                temperature=0.3
            )
            recommended_refs = refs_response.choices[0].message.content.strip().split("\n")

        # Generate complete prompt file
        prompt_file = await generate_prompt_file(request, topics, topic_details, recommended_refs)

        # Create response object explicitly setting cached=False
        response = PromptResponse(
            refined_prompt=refined,
            detected_topics=topics,
            recommended_references=recommended_refs if recommended_refs else None,
            cached=False,
            topic_details=topic_details,
            prompt_file_content=prompt_file
        )

        # Cache the response only if not in test environment or if explicitly testing caching
        if not is_test or "test_cache" in str(request.lazy_prompt):
            await redis.setex(
                cache_key,
                timedelta(seconds=CACHE_TTL),
                json.dumps(response.dict(exclude={'cached'}))  # Don't cache the cached flag
            )
        
        # Store the prompt in our storage system
        await prompt_storage.store_prompt(response, request)
        
        return response
    except Exception as e:
        logger.error(f"Error enhancing prompt: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error enhancing prompt: {str(e)}")

@app.post("/refine-prompt", response_model=PromptResponse)
async def refine_prompt(request: PromptRequest):
    if not request.lazy_prompt.strip():
        raise HTTPException(status_code=400, detail="Lazy prompt cannot be empty")
    
    logger.info("Refining prompt", extra={
        "lazy_prompt": request.lazy_prompt,
        "domain": request.domain,
        "expertise_level": request.expertise_level,
        "output_format": request.output_format
    })
    
    response = await enhance_prompt(request)
    
    logger.info("Prompt refined successfully", extra={
        "detected_topics": response.detected_topics,
        "has_references": bool(response.recommended_references),
        "cached": response.cached
    })
    
    return response

class SearchQuery(BaseModel):
    topic: str
    domain: Optional[DomainType] = None
    limit: Optional[int] = 5

class RelatedQuery(BaseModel):
    topics: List[str]
    domain: Optional[DomainType] = None
    limit: Optional[int] = 3

@app.post("/search/by-topic", response_model=List[PromptResponse])
async def search_prompts_by_topic(query: SearchQuery):
    """Search for existing prompts by topic"""
    if not query.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    
    results = await prompt_storage.search_by_topic(query.topic, query.limit)
    return [PromptResponse(**r["response"]) for r in results]

@app.post("/search/related", response_model=List[PromptResponse])
async def find_related_prompts(query: RelatedQuery):
    """Find related prompts based on topics"""
    if not query.topics:
        raise HTTPException(status_code=400, detail="Topics list cannot be empty")
    
    results = await prompt_storage.search_related(
        query.topics, 
        str(query.domain) if query.domain else None,
        query.limit
    )
    return [PromptResponse(**r["response"]) for r in results]

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)