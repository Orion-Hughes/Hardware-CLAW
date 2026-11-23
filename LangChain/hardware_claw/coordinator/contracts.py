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
    repair_from: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$',
        description='当前修订最近一次可定位的失败阶段交接ID。仅生成修订时传入。')


class ReadTaskEvidenceInput(StrictModel):
    kind: Literal['index', 'stage', 'source', 'simulation'] = 'index'
    ref: str | None = Field(default=None, max_length=180,
        description='stage使用交接ID，source使用已登记的工程相对路径，simulation使用MCP会话ID；省略则读当前仿真报告。')
    filename: str | None = Field(default=None, max_length=80, description='仿真证据清单中的文件；stage也可指定build.log或plan.json。')
    offset: int = Field(default=0, ge=0,
        description='从0开始的字符偏移，仅用于日志、plan.json或source_unit=characters；不是行号。')
    limit: int = Field(default=3000, ge=1, le=6000,
        description='最多读取的字符数，仅用于字符分页；源码默认按行读取，不使用这个字段。')
    source_unit: Literal['lines', 'characters'] = Field(default='lines',
        description='kind=source默认按行读取。只有明确需要字符分页时才选择characters。')
    start_line: int = Field(default=1, ge=1, description='源码起始行号，从1开始。')
    end_line: int | None = Field(default=None, ge=1,
        description='源码末行，包含该行。默认读取从start_line起最多120行；必要时用next_start_line续读。')


class DeliverInput(StrictModel):
    expected_task_version: int = Field(ge=0)
    expected_project_version: int = Field(ge=0)
    scope: Literal['checked_artifacts', 'verified'] = 'checked_artifacts'


class CompatibilityReview(StrictModel):
    verdict: Literal['compatible', 'conflict', 'unknown']
    hardware_ids: list[str] = Field(min_length=1, max_length=32)
    requirements: str = Field(min_length=1, max_length=600)
    interfaces: str = Field(min_length=1, max_length=600)
    resources: str = Field(min_length=1, max_length=600)
    electrical: str = Field(min_length=1, max_length=600)
    platform: str = Field(min_length=1, max_length=600)


class StageResult(StrictModel):
    """Small handoff, not a container for raw tool transcripts or source code."""
    status: Literal['completed', 'needs_input', 'blocked', 'failed', 'cancelled']
    summary: str = Field(min_length=1, max_length=2000)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    hardware_ids: list[str] = Field(default_factory=list, max_length=32)
    decisions: list[str] = Field(default_factory=list, max_length=20)
    blockers: list[str] = Field(default_factory=list, max_length=20)
    project_version: int | None = Field(default=None, ge=0)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    source_refs: list[str] = Field(default_factory=list, max_length=32)
    detail_ref: str | None = None
    verification_plan_ref: str | None = None
    compatibility: CompatibilityReview | None = None
    removed_hardware_ids: list[str] = Field(default_factory=list, max_length=32)
    change_reason: str | None = Field(default=None, max_length=1200)
    selection_update: dict | None = None
