"""Small project contracts, not a universal hardware IR."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Component(StrictModel):
    instance_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    hardware_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$")


class Connection(StrictModel):
    a: str = Field(min_length=3, max_length=80, description="Wokwi完整端点，例如mcu:4")
    b: str = Field(min_length=3, max_length=80, description="Wokwi完整端点，例如dht:SDA")


class Dependency(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)


class Design(StrictModel):
    goal: str = Field(min_length=1, max_length=2000)
    simulation_only: Literal[True]
    board_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$")
    components: list[Component] = Field(max_length=16)
    connections: list[Connection] = Field(max_length=80)
    dependencies: list[Dependency] = Field(max_length=20)
    assumptions: list[str] = Field(max_length=20)
    pin_defines: dict[str, int] = Field(default_factory=dict, description="源码需显式定义的GPIO常量，如DHT_PIN:4；检查器只验证简单整数定义。")


class UpdateDesignInput(StrictModel):
    expected_version: int = Field(ge=0)
    design: Design


class ReadFileInput(StrictModel):
    path: str = Field(min_length=1, max_length=180, description="files内相对路径；例如sketch.ino，不能访问项目外或.hwclaw。")


class WriteFilesInput(StrictModel):
    expected_version: int = Field(ge=0)
    files: dict[str, str] = Field(description="相对路径到完整UTF-8文本的映射；批量写入，最多32文件、每文件64000字节。")


class PatchInput(ReadFileInput):
    expected_version: int = Field(ge=0)
    old_text: str = Field(min_length=1, max_length=32000, description="必须恰好匹配一次的原文；不接受模糊补丁。")
    new_text: str = Field(max_length=32000)


class VersionInput(StrictModel):
    expected_version: int = Field(ge=0)
