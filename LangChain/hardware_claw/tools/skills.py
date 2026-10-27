"""Read only developer-maintained workflow guidance; no hardware facts duplicated."""
import hashlib
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from langchain.tools import tool
from .hardware_catalog import _invalid_input

SKILLS = {name: name + ".md" for name in ("wokwi_generation", "hardware_selection", "firmware_and_observation", "build_and_delivery", "simulation_feedback")}
ROOT = Path(__file__).resolve().parents[2] / "skills"


class SkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    skill_id: str = Field(default="", max_length=64, description="空字符串列出技能；wokwi_generation读取工程开发流程。")


@tool(args_schema=SkillInput)
def load_skill(skill_id: str = "") -> dict:
    """List or load a maintained development workflow, not hardware specifications.

    Use hardware tools for component facts. This tool cannot install or edit skills.
    """
    if not skill_id:
        data = {"skills": list(SKILLS)}
    elif skill_id not in SKILLS:
        return {"execution_status": "error", "error_code": "NOT_FOUND", "summary": "未找到技能。", "data": {"skills": list(SKILLS)}, "retryable": False}
    else:
        path = ROOT / SKILLS[skill_id]
        if path.is_symlink() or path.is_junction() or ROOT.is_symlink() or ROOT.is_junction():
            return {"execution_status": "error", "error_code": "INVALID_SOURCE", "summary": "技能路径不可用。", "data": None, "retryable": False}
        try:
            if path.stat().st_size > 16000:
                raise ValueError("oversize")
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            return {"execution_status": "error", "error_code": "INVALID_SOURCE", "summary": "技能文件缺失、过大或编码不可读。", "data": None, "retryable": False}
        data = {"skill_id": skill_id, "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest()}
    return {"execution_status": "ok", "error_code": None, "summary": "技能读取完成。", "data": data, "retryable": False}


load_skill.handle_validation_error = _invalid_input
