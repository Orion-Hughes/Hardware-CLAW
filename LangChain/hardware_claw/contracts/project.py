"""Small project contracts, not a universal hardware IR."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .. import limits


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Component(StrictModel):
    instance_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    hardware_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$")


class Connection(StrictModel):
    a: str = Field(min_length=3, max_length=80, description="Wokwi完整端点，例如mcu:4")
    b: str = Field(min_length=3, max_length=80, description="Wokwi完整端点，格式为元件实例ID:引脚名")


class Dependency(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)


class Design(StrictModel):
    goal: str = Field(min_length=1, max_length=2000)
    simulation_only: Literal[True]
    board_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$")
    components: list[Component] = Field(max_length=limits.COMPONENTS)
    connections: list[Connection] = Field(max_length=limits.CONNECTIONS)
    dependencies: list[Dependency] = Field(max_length=limits.DEPENDENCIES)
    assumptions: list[str] = Field(max_length=20)
    pin_defines: dict[str, int] = Field(default_factory=dict, description="源码需显式定义的GPIO常量名称与整数引脚编号；检查器只验证简单整数定义。")


class UpdateDesignInput(StrictModel):
    expected_version: int = Field(ge=0)
    design: Design


class ReadFileInput(StrictModel):
    path: str = Field(min_length=1, max_length=180, description="files内相对路径；例如sketch.ino，不能访问项目外或.hwclaw。")


class ReadFileRangeInput(ReadFileInput):
    start_line: int = Field(default=1, ge=1, description="从1开始的行号。")
    end_line: int | None = Field(default=None, ge=1, description="包含末行；null读到文件末尾。修改局部时按需读取行范围。")


class WriteFilesInput(StrictModel):
    expected_version: int = Field(ge=0)
    files: dict[str, str] = Field(description=f"相对路径到完整UTF-8文本的映射；最多{limits.PROJECT_FILES}文件、每文件{limits.FILE_BYTES}字节。受单次模型输出上限约束，应分批生成。")


class PatchInput(ReadFileInput):
    expected_version: int = Field(ge=0)
    old_text: str = Field(min_length=1, max_length=limits.PATCH_CHARACTERS, description="必须恰好匹配一次的原文；不接受模糊补丁。")
    new_text: str = Field(max_length=limits.PATCH_CHARACTERS)


class VersionInput(StrictModel):
    expected_version: int = Field(ge=0)
