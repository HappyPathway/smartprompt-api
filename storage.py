from abc import ABC, abstractmethod
from typing import List, Optional
import aioredis
import json
import time
from models import PromptResponse, PromptRequest

class PromptStorage(ABC):
    """Abstract base class for prompt storage implementations"""
    
    @abstractmethod
    async def store_prompt(self, prompt_data: PromptResponse, request: PromptRequest) -> str:
        """Store a prompt and return its ID"""
        pass

    @abstractmethod
    async def get_by_id(self, prompt_id: str) -> Optional[dict]:
        """Retrieve a prompt by ID"""
        pass

    @abstractmethod
    async def search_by_topic(self, topic: str, limit: int = 5) -> List[dict]:
        """Search prompts by topic"""
        pass

    @abstractmethod
    async def search_related(self, topics: List[str], domain: str = None, limit: int = 3) -> List[dict]:
        """Find related prompts"""
        pass

    @abstractmethod
    async def clear_cache(self):
        """Clear all cached data"""
        pass

class RedisPromptStorage(PromptStorage):
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.index_prefix = "prompt_index:"
        self.content_prefix = "prompt_content:"
        self.topics_prefix = "prompt_topics:"
        
    async def store_prompt(self, prompt_data: PromptResponse, request: PromptRequest) -> str:
        # Generate a unique ID for the prompt
        prompt_id = await self._generate_unique_id()
        
        # Store the main prompt content
        content = {
            "response": prompt_data.dict(),
            "request": request.dict()
        }
        await self.redis.set(
            f"{self.content_prefix}{prompt_id}",
            json.dumps(content)
        )
        
        # Index topics for searching
        for topic in prompt_data.detected_topics:
            await self.redis.sadd(f"{self.topics_prefix}{topic.lower()}", prompt_id)
            
        # Add to domain index if specified
        if request.domain:
            await self.redis.sadd(f"{self.index_prefix}domain:{request.domain}", prompt_id)
            
        return prompt_id
    
    async def get_by_id(self, prompt_id: str) -> Optional[dict]:
        content = await self.redis.get(f"{self.content_prefix}{prompt_id}")
        if content:
            return json.loads(content)
        return None
    
    async def search_by_topic(self, topic: str, limit: int = 5) -> List[dict]:
        # Get prompt IDs for the topic
        prompt_ids = await self.redis.smembers(f"{self.topics_prefix}{topic.lower()}")
        results = []
        
        # Fetch content for each ID
        for prompt_id in prompt_ids:
            if len(results) >= limit:
                break
            content = await self.get_by_id(prompt_id)
            if content:
                results.append(content)
                
        return results
    
    async def search_related(self, topics: List[str], domain: str = None, limit: int = 3) -> List[dict]:
        results = []
        seen_ids = set()
        
        # Search by topics first
        for topic in topics:
            if len(results) >= limit:
                break
                
            prompt_ids = await self.redis.smembers(f"{self.topics_prefix}{topic.lower()}")
            
            # If domain is specified, filter by domain
            if domain:
                domain_ids = await self.redis.smembers(f"{self.index_prefix}domain:{domain}")
                prompt_ids = prompt_ids.intersection(domain_ids)
            
            # Get content for each ID
            for prompt_id in prompt_ids:
                if prompt_id in seen_ids or len(results) >= limit:
                    continue
                    
                content = await self.get_by_id(prompt_id)
                if content:
                    results.append(content)
                    seen_ids.add(prompt_id)
                    
        return results
    
    async def clear_cache(self):
        """Clear all cached data"""
        # Get all keys with our prefixes
        keys_to_delete = []
        for prefix in [self.index_prefix, self.content_prefix, self.topics_prefix]:
            async for key in self.redis.scan_iter(f"{prefix}*"):
                keys_to_delete.append(key)
        
        # Delete all keys if any exist
        if keys_to_delete:
            await self.redis.delete(*keys_to_delete)
            
    async def _generate_unique_id(self) -> str:
        """Generate a unique ID for a new prompt"""
        while True:
            # Generate a random ID
            prompt_id = str(hash(f"{time.time()}"))[1:13]
            # Check if it exists
            exists = await self.redis.exists(f"{self.content_prefix}{prompt_id}")
            if not exists:
                return prompt_id