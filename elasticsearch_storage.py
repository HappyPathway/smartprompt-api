from elasticsearch import AsyncElasticsearch
from .storage import PromptStorage
from typing import Optional, List, Dict, Any
from datetime import datetime
import openai

class ElasticsearchPromptStorage(PromptStorage):
    """Elasticsearch implementation of prompt storage"""
    
    def __init__(self, es_hosts: List[str], index_prefix: str = "prompts"):
        self.client = AsyncElasticsearch(hosts=es_hosts)
        self.index_prefix = index_prefix

    async def setup(self):
        """Initialize Elasticsearch indices and mappings"""
        mapping = {
            "mappings": {
                "properties": {
                    "lazy_prompt": {"type": "text", "analyzer": "english"},
                    "refined_prompt": {"type": "text", "analyzer": "english"},
                    "domain": {"type": "keyword"},
                    "expertise_level": {"type": "keyword"},
                    "detected_topics": {
                        "type": "text",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "embedding_vector": {"type": "dense_vector", "dims": 1536},
                    "created_at": {"type": "date"},
                    "metadata": {"type": "object"}
                }
            },
            "settings": {
                "analysis": {
                    "analyzer": {
                        "technical_terms": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "stop"]
                        }
                    }
                }
            }
        }
        
        await self.client.indices.create(
            index=f"{self.index_prefix}-v1",
            body=mapping,
            ignore=400  # Ignore error if index already exists
        )

    async def store_prompt(self, prompt_data: PromptResponse, request: PromptRequest) -> str:
        """Store a prompt and return its ID"""
        try:
            # Generate embedding for semantic search
            embedding = await self._generate_embedding(prompt_data.refined_prompt)
            
            document = {
                "lazy_prompt": request.lazy_prompt,
                "refined_prompt": prompt_data.refined_prompt,
                "domain": request.domain,
                "expertise_level": request.expertise_level,
                "detected_topics": prompt_data.detected_topics,
                "embedding_vector": embedding,
                "created_at": datetime.utcnow().isoformat(),
                "metadata": {
                    "output_format": request.output_format,
                    "include_best_practices": request.include_best_practices,
                    "include_examples": request.include_examples,
                }
            }
            
            result = await self.client.index(
                index=f"{self.index_prefix}-v1",
                document=document
            )
            return result["_id"]
            
        except Exception as e:
            logger.error(f"Error storing prompt in Elasticsearch: {str(e)}")
            raise

    async def get_by_id(self, prompt_id: str) -> Optional[dict]:
        """Retrieve a prompt by ID"""
        try:
            result = await self.client.get(
                index=f"{self.index_prefix}-v1",
                id=prompt_id
            )
            return result["_source"] if result["found"] else None
        except Exception as e:
            logger.error(f"Error retrieving prompt from Elasticsearch: {str(e)}")
            return None

    async def search_by_topic(self, topic: str, limit: int = 5) -> List[dict]:
        """Search prompts by topic using text and vector similarity"""
        try:
            # Generate embedding for the topic
            topic_embedding = await self._generate_embedding(topic)
            
            # Hybrid search query combining text and vector similarity
            query = {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": topic,
                                "fields": [
                                    "detected_topics^3",
                                    "lazy_prompt^2",
                                    "refined_prompt"
                                ],
                                "fuzziness": "AUTO"
                            }
                        },
                        {
                            "script_score": {
                                "query": {"match_all": {}},
                                "script": {
                                    "source": "cosineSimilarity(params.query_vector, 'embedding_vector') + 1.0",
                                    "params": {"query_vector": topic_embedding}
                                }
                            }
                        }
                    ]
                }
            }
            
            results = await self.client.search(
                index=f"{self.index_prefix}-v1",
                body={"query": query, "size": limit}
            )
            
            return [hit["_source"] for hit in results["hits"]["hits"]]
            
        except Exception as e:
            logger.error(f"Error searching prompts in Elasticsearch: {str(e)}")
            return []

    async def search_related(self, topics: List[str], domain: str = None, limit: int = 3) -> List[dict]:
        """Find related prompts using multi-match and domain filtering"""
        try:
            query = {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": " ".join(topics),
                                "fields": [
                                    "detected_topics^3",
                                    "lazy_prompt^2",
                                    "refined_prompt"
                                ],
                                "type": "cross_fields",
                                "operator": "or"
                            }
                        }
                    ]
                }
            }
            
            if domain:
                query["bool"]["filter"] = [{"term": {"domain": domain}}]
            
            results = await self.client.search(
                index=f"{self.index_prefix}-v1",
                body={"query": query, "size": limit}
            )
            
            return [hit["_source"] for hit in results["hits"]["hits"]]
            
        except Exception as e:
            logger.error(f"Error finding related prompts in Elasticsearch: {str(e)}")
            return []

    async def clear_cache(self):
        """Clear all indexed data"""
        try:
            await self.client.indices.delete(
                index=f"{self.index_prefix}-v1",
                ignore=[404]
            )
            await self.setup()
        except Exception as e:
            logger.error(f"Error clearing Elasticsearch index: {str(e)}")

    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text using OpenAI"""
        try:
            client = openai.AsyncClient()
            response = await client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return [0.0] * 1536  # Return zero vector as fallback

    async def close(self):
        """Close Elasticsearch client connection"""
        await self.client.close()