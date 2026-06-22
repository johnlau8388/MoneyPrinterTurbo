from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


PetSpecies = Literal["dog", "cat", "other"]
PlanStatus = Literal["planned", "generating", "generated", "failed"]


class PetProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    species: PetSpecies = "dog"
    description: str = Field(default="", max_length=1000)
    image_files: list[str] = Field(default_factory=list)
    active: bool = True
    language: str = Field(default="zh-CN", max_length=64)
    daily_time: Optional[str] = None
    topic_templates: list[str] = Field(default_factory=list)
    style_prompt: str = Field(default="", max_length=2000)
    video_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("daily_time")
    @classmethod
    def validate_daily_time(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("daily_time must use HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("daily_time must use HH:MM format")
        return f"{hour:02d}:{minute:02d}"


class PetProfile(PetProfileCreate):
    pet_id: str
    created_at: str
    updated_at: str


class PetProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    species: Optional[PetSpecies] = None
    description: Optional[str] = Field(default=None, max_length=1000)
    image_files: Optional[list[str]] = None
    active: Optional[bool] = None
    language: Optional[str] = Field(default=None, max_length=64)
    daily_time: Optional[str] = None
    topic_templates: Optional[list[str]] = None
    style_prompt: Optional[str] = Field(default=None, max_length=2000)
    video_params: Optional[dict[str, Any]] = None

    @field_validator("daily_time")
    @classmethod
    def validate_daily_time(cls, value: Optional[str]) -> Optional[str]:
        return PetProfileCreate.validate_daily_time(value)


class GeneratePetVideoRequest(BaseModel):
    topic: str = Field(default="", max_length=500)
    script: str = Field(default="", max_length=8000)
    plan_date: Optional[str] = None
    force: bool = False
    video_params: dict[str, Any] = Field(default_factory=dict)


class PetContentPlan(BaseModel):
    plan_id: str
    pet_id: str
    plan_date: str
    topic: str
    script: str = ""
    status: PlanStatus = "planned"
    task_id: Optional[str] = None
    videos: list[str] = Field(default_factory=list)
    error_message: str = ""
    created_at: str
    updated_at: str


class SchedulerStatus(BaseModel):
    enabled: bool
    running: bool
    daily_time: str
