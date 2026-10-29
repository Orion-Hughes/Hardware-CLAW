"""Read developer-maintained workflow packages; never execute or install them."""
from pydantic import BaseModel, ConfigDict, Field
from langchain.tools import tool
from .hardware_catalog import _invalid_input
from ..skill_catalog import SkillCatalog, SkillError


class SkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    skill_id: str = Field(default="", max_length=64, description="空字符串列出技能用途目录；指定ID加载正文。")
    reference: str = Field(default="", max_length=180, description="按需读取该技能返回的references路径；空字符串读取SKILL.md。")
    offset: int = Field(default=0, ge=0, le=64000)
    limit: int = Field(default=6000, ge=1, le=12000)


@tool(args_schema=SkillInput)
def load_skill(skill_id: str = "", reference: str = "", offset: int = 0, limit: int = 6000) -> dict:
    """Discover or load workflow packages and their own paginated references.

    Load relevant skills only. Component facts and exact driver APIs belong in
    hardware tools and get_driver_api. tool_groups describe use, not permissions.
    """
    try:
        if not skill_id and reference:
            raise SkillError("INVALID_ARGUMENT", "读取参考资料需要skill_id。")
        catalog = SkillCatalog()
        data = catalog.load(skill_id, reference, offset, limit) if skill_id else catalog.catalog()
        return {"execution_status": "ok", "error_code": None, "summary": "技能读取完成。", "data": data, "retryable": False}
    except SkillError as exc:
        return {"execution_status": "error", "error_code": exc.code, "summary": str(exc), "data": None, "retryable": False}


load_skill.handle_validation_error = _invalid_input
