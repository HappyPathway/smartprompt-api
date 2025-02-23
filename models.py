from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

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
    topic_details: Optional[dict] = Field(None, description="Detailed information about each detected topic")
    prompt_file_content: Optional[str] = Field(None, description="Complete prompt file in markdown format")