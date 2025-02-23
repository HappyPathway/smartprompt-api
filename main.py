from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
import logging
from pythonjsonlogger import jsonlogger
import uvicorn
import re
import os
from typing import Optional, List
from enum import Enum
import openai
from dotenv import load_dotenv
import aioredis
import json
from prometheus_fastapi_instrumentator import Instrumentator
import hashlib
from datetime import timedelta

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

app = FastAPI(
    title="Smart Prompt API",
    description="API for refining 'lazy' prompts into high-quality prompts using AI",
    version="1.0.0"
)

# Add Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Redis connection pool
redis = None

@app.on_event("startup")
async def startup_event():
    global redis
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)

@app.on_event("shutdown")
async def shutdown_event():
    if redis:
        await redis.close()

class DomainType(str, Enum):
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    GENERAL = "general"

class ExpertiseLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"

class OutputFormat(str, Enum):
    SIMPLE = "simple"
    DETAILED = "detailed"
    TUTORIAL = "tutorial"
    CHECKLIST = "checklist"

class PromptRequest(BaseModel):
    lazy_prompt: str = Field(..., description="The simple prompt to be refined")
    domain: Optional[DomainType] = Field(DomainType.GENERAL, description="The technical domain of the prompt")
    expertise_level: Optional[ExpertiseLevel] = Field(ExpertiseLevel.INTERMEDIATE, description="Target expertise level")
    output_format: Optional[OutputFormat] = Field(OutputFormat.DETAILED, description="Desired output format")
    include_best_practices: Optional[bool] = Field(True, description="Include industry best practices")
    include_examples: Optional[bool] = Field(True, description="Include examples in the response")

class PromptResponse(BaseModel):
    refined_prompt: str
    detected_topics: List[str]
    recommended_references: Optional[List[str]]
    cached: bool = Field(False, description="Whether the response was served from cache")

def generate_cache_key(request: PromptRequest) -> str:
    """Generate a unique cache key for a prompt request."""
    key_data = {
        "lazy_prompt": request.lazy_prompt,
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
    """Health check endpoint that verifies Redis connectivity."""
    try:
        await redis.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Redis health check failed: {str(e)}")

async def detect_topics(prompt: str) -> List[str]:
    """Use OpenAI to detect key technical topics in the prompt."""
    try:
        response = await openai.ChatCompletion.acreate(
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

async def enhance_prompt(request: PromptRequest) -> PromptResponse:
    """
    Transform a lazy prompt into a sophisticated one using OpenAI,
    incorporating domain expertise, best practices, and proper structure.
    """
    # Check cache first
    cache_key = generate_cache_key(request)
    cached_response = await redis.get(cache_key)
    if cached_response:
        response_data = json.loads(cached_response)
        return PromptResponse(**response_data, cached=True)

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

    # Detect technical topics
    topics = await detect_topics(request.lazy_prompt)

    try:
        # Build the enhanced prompt
        messages = [
            {"role": "system", "content": f"{system_prompts[request.domain]}\n\nRespond as if explaining to a {request.expertise_level} level technologist."},
            {"role": "user", "content": f"""
Enhance and respond to this prompt: {request.lazy_prompt}

Format: {format_templates[request.output_format]}

{
    'Include relevant industry best practices and standards.\n' if request.include_best_practices else ''
}{
    'Provide specific technical examples where appropriate.\n' if request.include_examples else ''
}
"""}
        ]

        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )

        refined = response.choices[0].message.content.strip()

        # Get recommended references if best practices are requested
        recommended_refs = []
        if request.include_best_practices:
            refs_response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a technical documentation expert. Suggest relevant technical documentation, standards, or best practice guides."},
                    {"role": "user", "content": f"Suggest 2-3 technical references or documentation relevant to: {request.lazy_prompt}"}
                ],
                max_tokens=150,
                temperature=0.3
            )
            recommended_refs = refs_response.choices[0].message.content.strip().split("\n")

        response = PromptResponse(
            refined_prompt=refined,
            detected_topics=topics,
            recommended_references=recommended_refs if recommended_refs else None,
            cached=False
        )

        # Cache the response
        await redis.setex(
            cache_key,
            timedelta(seconds=CACHE_TTL),
            json.dumps(response.dict(exclude={'cached'}))
        )

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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)