from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch, AsyncMock
from main import app, enhance_prompt, detect_topics, DomainType, ExpertiseLevel, OutputFormat

client = TestClient(app)

# Mock OpenAI responses
MOCK_TOPIC_RESPONSE = AsyncMock(return_value={
    "choices": [{
        "message": {"content": "Terraform\nInfrastructure as Code\nCloud Architecture"}
    }]
})

MOCK_COMPLETION_RESPONSE = AsyncMock(return_value={
    "choices": [{
        "message": {"content": "Enhanced prompt content"}
    }]
})

MOCK_REFS_RESPONSE = AsyncMock(return_value={
    "choices": [{
        "message": {"content": "Terraform Documentation\nAWS Best Practices Guide"}
    }]
})

@pytest.fixture(autouse=True)
def mock_openai():
    with patch("openai.ChatCompletion.acreate") as mock:
        mock.side_effect = [
            MOCK_TOPIC_RESPONSE(),
            MOCK_COMPLETION_RESPONSE(),
            MOCK_REFS_RESPONSE()
        ]
        yield mock

def test_empty_prompt():
    response = client.post("/refine-prompt", json={"lazy_prompt": ""})
    assert response.status_code == 400
    assert response.json()["detail"] == "Lazy prompt cannot be empty"

def test_valid_prompt_basic():
    response = client.post("/refine-prompt", json={
        "lazy_prompt": "what is terraform"
    })
    assert response.status_code == 200
    result = response.json()
    assert "refined_prompt" in result
    assert "detected_topics" in result
    assert isinstance(result["detected_topics"], list)

def test_valid_prompt_full_options():
    response = client.post("/refine-prompt", json={
        "lazy_prompt": "what is terraform",
        "domain": "infrastructure",
        "expertise_level": "expert",
        "output_format": "tutorial",
        "include_best_practices": True,
        "include_examples": True
    })
    assert response.status_code == 200
    result = response.json()
    assert "refined_prompt" in result
    assert "detected_topics" in result
    assert "recommended_references" in result

def test_malformed_request():
    response = client.post("/refine-prompt", json={"wrong_field": "test"})
    assert response.status_code == 422  # Pydantic validation error

def test_invalid_domain():
    response = client.post("/refine-prompt", json={
        "lazy_prompt": "what is terraform",
        "domain": "invalid_domain"
    })
    assert response.status_code == 422

def test_invalid_expertise_level():
    response = client.post("/refine-prompt", json={
        "lazy_prompt": "what is terraform",
        "expertise_level": "invalid_level"
    })
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_detect_topics():
    topics = await detect_topics("what is terraform")
    assert len(topics) > 0
    assert isinstance(topics, list)
    assert all(isinstance(topic, str) for topic in topics)

@pytest.mark.asyncio
async def test_enhance_prompt_full():
    from main import PromptRequest
    request = PromptRequest(
        lazy_prompt="what is terraform",
        domain=DomainType.INFRASTRUCTURE,
        expertise_level=ExpertiseLevel.EXPERT,
        output_format=OutputFormat.TUTORIAL,
        include_best_practices=True,
        include_examples=True
    )
    response = await enhance_prompt(request)
    assert response.refined_prompt
    assert response.detected_topics
    assert response.recommended_references