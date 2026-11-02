from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Stage = Literal['selection', 'generation', 'verification']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class RunStageInput(StrictModel):
    stage: Stage
    objective: str = Field(min_length=1, max_length=3000)
    expected_task_version: int = Field(ge=0)
    input_refs: list[str] = Field(default_factory=list, max_length=8,
        description='get_task_state返回的当前任务交接ID，不接受文件路径。宿主自动补入必要的最新交接。')
    expected_project_version: int | None = Field(default=None, ge=0)


class DeliverInput(StrictModel):
    expected_task_version: int = Field(ge=0)
    expected_project_version: int = Field(ge=0)
    scope: Literal['checked_artifacts', 'verified'] = 'checked_artifacts'


class StageResult(StrictModel):
    """Small handoff, not a container for raw tool transcripts or source code."""
    status: Literal['completed', 'needs_input', 'blocked', 'failed', 'cancelled']
    summary: str = Field(min_length=1, max_length=2000)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    hardware_ids: list[str] = Field(default_factory=list, max_length=32)
    decisions: list[str] = Field(default_factory=list, max_length=20)
    blockers: list[str] = Field(default_factory=list, max_length=20)
    next_stage: Stage | None = None
    project_version: int | None = Field(default=None, ge=0)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    source_refs: list[str] = Field(default_factory=list, max_length=32)
    detail_ref: str | None = None
