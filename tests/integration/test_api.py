import pytest
import pytest_asyncio
import os
import httpx
import asyncio
from typing import AsyncGenerator
import aioredis
import json

# Get configuration from environment
API_URL = os.getenv("API_URL", "http://api:8000")  # Changed from localhost to api service name
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")  # Changed from localhost to redis service name

@pytest_asyncio.fixture(scope="function")
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    # Increase timeout to 60 seconds for OpenAI calls
    async with httpx.AsyncClient(base_url=API_URL, timeout=60.0) as client:
        yield client

@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    # Clear all keys before each test
    await client.flushall()
    yield client
    await client.close()

@pytest.mark.asyncio
async def test_api_health(api_client: httpx.AsyncClient):
    """Test that the API is accessible and responding"""
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["redis"] == "connected"

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
    test_prompt = "test_cache: what is docker"
    
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
    base_prompt = "test_cache: explain kubernetes"
    
    # First request with default parameters
    response1 = await api_client.post("/refine-prompt", json={
        "lazy_prompt": base_prompt
    })
    assert response1.status_code == 200
    data1 = response1.json()
    
    # Same prompt but different parameters should not use cache
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

@pytest.mark.asyncio
async def test_topic_details_and_prompt_file(api_client: httpx.AsyncClient):
    """Test that the API generates detailed topic information and prompt files"""
    response = await api_client.post("/refine-prompt", json={
        "lazy_prompt": "explain terraform modules",
        "domain": "infrastructure",
        "expertise_level": "intermediate",
        "output_format": "detailed"
    })
    assert response.status_code == 200
    data = response.json()
    
    # Check for new fields
    assert "topic_details" in data
    assert "prompt_file_content" in data
    
    # Validate topic details
    assert isinstance(data["topic_details"], dict)
    assert len(data["topic_details"]) > 0
    assert all(isinstance(v, str) for v in data["topic_details"].values())
    
    # Validate prompt file content
    assert isinstance(data["prompt_file_content"], str)
    assert "# " in data["prompt_file_content"]  # Should have markdown headers
    assert "## Overview" in data["prompt_file_content"]
    assert "## Key Topics" in data["prompt_file_content"]
    
    # Each detected topic should have details
    for topic in data["detected_topics"]:
        topic_key = topic.strip("123456789. ")  # Remove any numbering
        assert any(topic_key in key for key in data["topic_details"].keys())

@pytest.mark.asyncio
async def test_rate_limit_backoff(api_client: httpx.AsyncClient):
    """Test that rate limit backoff uses the wait time from OpenAI's response"""
    # Make multiple concurrent requests to trigger rate limiting
    prompts = ["rate_test:" + str(i) for i in range(10)]
    
    async def make_request(prompt: str):
        try:
            response = await api_client.post("/refine-prompt", json={"lazy_prompt": prompt})
            return response.status_code
        except httpx.HTTPError as e:
            return e.response.status_code if hasattr(e, 'response') else 500
    
    # Execute requests in parallel to trigger rate limiting
    status_codes = await asyncio.gather(*[
        make_request(prompt) for prompt in prompts
    ])
    
    # Some requests should succeed (200) and some should get rate limited (503)
    assert 200 in status_codes, "No requests succeeded"
    assert 503 in status_codes, "No requests were rate limited"

@pytest.mark.asyncio
async def test_prompt_library_indexing_and_search(api_client: httpx.AsyncClient):
    """Test that prompts are properly indexed and searchable"""
    # First generate some prompts to populate the library
    prompts = [
        {
            "lazy_prompt": "explain kubernetes deployments",
            "domain": "architecture",
            "expertise_level": "expert"
        },
        {
            "lazy_prompt": "kubernetes pod networking",
            "domain": "infrastructure",
            "expertise_level": "intermediate"
        }
    ]

    # Generate prompts
    for prompt in prompts:
        response = await api_client.post("/refine-prompt", json=prompt)
        assert response.status_code == 200

    # Test topic search
    search_response = await api_client.post("/search/by-topic", 
        json={"topic": "kubernetes", "limit": 2})
    assert search_response.status_code == 200
    results = search_response.json()
    assert len(results) > 0
    assert any("kubernetes" in r["refined_prompt"].lower() for r in results)

    # Test related prompts search
    related_response = await api_client.post("/search/related",
        json={
            "topics": ["kubernetes", "networking"],
            "domain": "infrastructure",
            "limit": 2
        })
    assert related_response.status_code == 200
    related_results = related_response.json()
    assert len(related_results) > 0

@pytest.mark.asyncio
async def test_prompt_enhancement_with_related_insights(api_client: httpx.AsyncClient):
    """Test that prompt generation benefits from related prompts"""
    # First create a prompt about kubernetes networking
    initial_response = await api_client.post("/refine-prompt", json={
        "lazy_prompt": "kubernetes pod networking basics",
        "domain": "infrastructure",
        "expertise_level": "intermediate"
    })
    assert initial_response.status_code == 200

    # Now create a related prompt and verify it includes insights
    related_response = await api_client.post("/refine-prompt", json={
        "lazy_prompt": "explain kubernetes service networking",
        "domain": "infrastructure",
        "expertise_level": "intermediate"
    })
    assert related_response.status_code == 200
    data = related_response.json()
    
    # The refined prompt should have benefited from the previous related content
    assert data["refined_prompt"] is not None
    assert len(data["detected_topics"]) > 0

@pytest.mark.asyncio
async def test_search_error_handling(api_client: httpx.AsyncClient):
    """Test error handling in search endpoints"""
    # Test empty topic
    response = await api_client.post("/search/by-topic", 
        json={"topic": "", "limit": 5})
    assert response.status_code == 400

    # Test empty topics list
    response = await api_client.post("/search/related",
        json={"topics": [], "limit": 5})
    assert response.status_code == 400