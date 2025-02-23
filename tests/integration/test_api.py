import pytest
import os
import httpx
import asyncio
from typing import AsyncGenerator
import aioredis
import json

# Get configuration from environment
API_URL = os.getenv("API_URL", "http://localhost:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

@pytest.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        yield client

@pytest.fixture
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    yield client
    await client.close()

@pytest.mark.asyncio
async def test_api_health(api_client: httpx.AsyncClient):
    """Test that the API is accessible and responding"""
    response = await api_client.get("/docs")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_basic_prompt_refinement(api_client: httpx.AsyncClient):
    """Test basic prompt refinement functionality"""
    response = await api_client.post("/refine-prompt", json={
        "lazy_prompt": "what is docker"
    })
    assert response.status_code == 200
    data = response.json()
    assert "refined_prompt" in data
    assert "detected_topics" in data

@pytest.mark.asyncio
async def test_advanced_prompt_refinement(api_client: httpx.AsyncClient):
    """Test advanced prompt refinement with all options"""
    response = await api_client.post("/refine-prompt", json={
        "lazy_prompt": "explain kubernetes architecture",
        "domain": "architecture",
        "expertise_level": "expert",
        "output_format": "tutorial",
        "include_best_practices": True,
        "include_examples": True
    })
    assert response.status_code == 200
    data = response.json()
    assert "refined_prompt" in data
    assert "detected_topics" in data
    assert "recommended_references" in data
    assert len(data["detected_topics"]) > 0

@pytest.mark.asyncio
async def test_error_handling(api_client: httpx.AsyncClient):
    """Test API error handling"""
    # Test empty prompt
    response = await api_client.post("/refine-prompt", json={
        "lazy_prompt": ""
    })
    assert response.status_code == 400
    
    # Test invalid domain
    response = await api_client.post("/refine-prompt", json={
        "lazy_prompt": "test",
        "domain": "invalid_domain"
    })
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_concurrent_requests(api_client: httpx.AsyncClient):
    """Test handling of concurrent requests"""
    prompts = [
        "what is terraform",
        "explain docker",
        "describe kubernetes",
        "explain microservices"
    ]
    
    async def make_request(prompt: str):
        return await api_client.post("/refine-prompt", json={"lazy_prompt": prompt})
    
    responses = await asyncio.gather(*[
        make_request(prompt) for prompt in prompts
    ])
    
    assert all(r.status_code == 200 for r in responses)
    data = [r.json() for r in responses]
    assert all("refined_prompt" in d for d in data)

@pytest.mark.asyncio
async def test_basic_prompt_refinement_with_cache(api_client: httpx.AsyncClient, redis_client: aioredis.Redis):
    """Test that prompt refinement works and uses caching properly"""
    test_prompt = "what is docker"
    
    # First request should not be cached
    response1 = await api_client.post("/refine-prompt", json={
        "lazy_prompt": test_prompt
    })
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["cached"] is False
    
    # Second request should be cached
    response2 = await api_client.post("/refine-prompt", json={
        "lazy_prompt": test_prompt
    })
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["cached"] is True
    assert data2["refined_prompt"] == data1["refined_prompt"]

@pytest.mark.asyncio
async def test_cache_with_different_parameters(api_client: httpx.AsyncClient):
    """Test that cache varies with different request parameters"""
    base_prompt = "explain kubernetes"
    
    # First request with default parameters
    response1 = await api_client.post("/refine-prompt", json={
        "lazy_prompt": base_prompt
    })
    assert response1.status_code == 200
    data1 = response1.json()
    
    # Same prompt but different parameters should not be cached
    response2 = await api_client.post("/refine-prompt", json={
        "lazy_prompt": base_prompt,
        "domain": "architecture",
        "expertise_level": "expert"
    })
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["cached"] is False
    assert data2["refined_prompt"] != data1["refined_prompt"]

@pytest.mark.asyncio
async def test_health_check(api_client: httpx.AsyncClient):
    """Test the health check endpoint"""
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["redis"] == "connected"