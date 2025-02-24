from typing import Optional, List, Dict, Any
from storage import PromptStorage
from redis_storage import RedisPromptStorage
from elasticsearch_storage import ElasticsearchPromptStorage
import logging

logger = logging.getLogger(__name__)

class HybridPromptStorage(PromptStorage):
    """
    Hybrid storage implementation that can write to both Redis and Elasticsearch
    and gradually shift read operations from Redis to Elasticsearch
    """
    
    def __init__(self, redis_storage: RedisPromptStorage, es_storage: ElasticsearchPromptStorage):
        self.redis = redis_storage
        self.elasticsearch = es_storage
        self.es_read_percentage = 0  # 0-100: percentage of reads to route to Elasticsearch
        self.shadow_write = True  # Write to both systems
        self.compare_results = True  # Compare results between systems

    async def store_prompt(self, prompt_data: PromptResponse, request: PromptRequest) -> str:
        """Store prompt in one or both storage systems"""
        redis_id = await self.redis.store_prompt(prompt_data, request)
        
        if self.shadow_write:
            try:
                es_id = await self.elasticsearch.store_prompt(prompt_data, request)
                if redis_id != es_id:
                    logger.warning(f"Storage ID mismatch: Redis={redis_id}, ES={es_id}")
            except Exception as e:
                logger.error(f"Elasticsearch shadow write failed: {str(e)}")
        
        return redis_id

    async def get_by_id(self, prompt_id: str) -> Optional[dict]:
        """Get prompt by ID with configurable routing"""
        if self._should_use_elasticsearch():
            try:
                es_result = await self.elasticsearch.get_by_id(prompt_id)
                if es_result:
                    if self.compare_results:
                        redis_result = await self.redis.get_by_id(prompt_id)
                        if redis_result and redis_result != es_result:
                            logger.warning(f"Result mismatch for ID {prompt_id}")
                    return es_result
            except Exception as e:
                logger.error(f"Elasticsearch get failed: {str(e)}")
        
        return await self.redis.get_by_id(prompt_id)

    async def search_by_topic(self, topic: str, limit: int = 5) -> List[dict]:
        """Search prompts by topic with result comparison"""
        if self._should_use_elasticsearch():
            try:
                es_results = await self.elasticsearch.search_by_topic(topic, limit)
                if self.compare_results:
                    redis_results = await self.redis.search_by_topic(topic, limit)
                    self._compare_search_results(redis_results, es_results, "topic")
                return es_results
            except Exception as e:
                logger.error(f"Elasticsearch search failed: {str(e)}")
        
        return await self.redis.search_by_topic(topic, limit)

    async def search_related(self, topics: List[str], domain: str = None, limit: int = 3) -> List[dict]:
        """Find related prompts with result comparison"""
        if self._should_use_elasticsearch():
            try:
                es_results = await self.elasticsearch.search_related(topics, domain, limit)
                if self.compare_results:
                    redis_results = await self.redis.search_related(topics, domain, limit)
                    self._compare_search_results(redis_results, es_results, "related")
                return es_results
            except Exception as e:
                logger.error(f"Elasticsearch related search failed: {str(e)}")
        
        return await self.redis.search_related(topics, domain, limit)

    async def clear_cache(self):
        """Clear both storage systems"""
        await self.redis.clear_cache()
        if self.shadow_write:
            await self.elasticsearch.clear_cache()

    def _should_use_elasticsearch(self) -> bool:
        """Determine if this operation should use Elasticsearch"""
        import random
        return random.randint(1, 100) <= self.es_read_percentage

    def _compare_search_results(self, redis_results: List[dict], es_results: List[dict], search_type: str):
        """Compare results between storage systems and log discrepancies"""
        redis_ids = {r.get('id') for r in redis_results}
        es_ids = {r.get('id') for r in es_results}
        
        if redis_ids != es_ids:
            logger.warning(
                f"{search_type} search result mismatch:\n"
                f"Only in Redis: {redis_ids - es_ids}\n"
                f"Only in Elasticsearch: {es_ids - redis_ids}"
            )

    def increase_es_percentage(self, increment: int = 10):
        """Gradually increase the percentage of reads routed to Elasticsearch"""
        self.es_read_percentage = min(100, self.es_read_percentage + increment)
        logger.info(f"Elasticsearch read percentage increased to {self.es_read_percentage}%")

    def set_shadow_write(self, enabled: bool):
        """Enable or disable shadow writes to Elasticsearch"""
        self.shadow_write = enabled
        logger.info(f"Shadow write to Elasticsearch {'enabled' if enabled else 'disabled'}")

    def set_result_comparison(self, enabled: bool):
        """Enable or disable result comparison between storage systems"""
        self.compare_results = enabled
        logger.info(f"Result comparison {'enabled' if enabled else 'disabled'}")