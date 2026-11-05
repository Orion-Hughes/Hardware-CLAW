"""Small project contracts, not a universal hardware IR."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .. import limits


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Component(StrictModel):
    instance_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$",
        description="工程内唯一外设实例ID，用于连接端点；mcu保留给自动创建的主板，禁止用于外设。同型号多个实例须使用不同instance_id。")
    hardware_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$",
        description="知识库返回的稳定外设ID，不是instance_id或Wokwi part_type；不得放入板卡。")


class Connection(StrictModel):
    a: str = Field(min_length=3, max_length=80, description="实例ID:模型引脚名，板卡实例固定mcu，例如mcu:4；使用资料中的精确端点名，不能填硬件库ID。")
    b: str = Field(min_length=3, max_length=80, description="实例ID:模型引脚名；外设实例须在components声明。与a连接，不允许自连或重复无向连接。")


class Dependency(StrictModel):
    name: str = Field(min_length=1, max_length=100, description="所选硬件资料登记的正式库名称，不是头文件名或任意下载URL。")
    version: str = Field(min_length=1, max_length=40, description="所选硬件资料登记的固定版本，不使用latest或版本范围。")


class Design(StrictModel):
    goal: str = Field(min_length=1, max_length=2000)
    simulation_only: Literal[True]
    board_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$",
        description="知识库主板ID；宿主自动创建instance_id=mcu。主板只在此声明，不能再加入components。")
    components: list[Component] = Field(max_length=limits.COMPONENTS,
        description="仅列外设实例，不含主板；无外设时为空。每个instance_id唯一且不能为mcu。")
    connections: list[Connection] = Field(max_length=limits.CONNECTIONS,
        description="完整信号与电源连线；使用mcu及components中的实例ID，端点来自所选Wokwi模型。")
    dependencies: list[Dependency] = Field(max_length=limits.DEPENDENCIES)
    assumptions: list[str] = Field(max_length=20)
    pin_defines: dict[str, int] = Field(default_factory=dict, description="源码需显式定义的GPIO常量名称与整数引脚编号；检查器只验证简单整数定义。")


class UpdateDesignInput(StrictModel):
    expected_version: int = Field(ge=0, description="get_project或最近成功写操作返回的version；失败不代表版本增加，冲突时重新get_project。")
    design: Design = Field(description="完整替换设计，不是增量补丁；只在board_id声明主板，components只包含外设。")


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
