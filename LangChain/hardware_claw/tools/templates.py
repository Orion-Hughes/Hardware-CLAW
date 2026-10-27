"""Read-only, explicitly registered templates; never accept filesystem paths."""
import hashlib
from pathlib import Path
from langchain.tools import tool

ROOT = Path(__file__).resolve().parents[2] / "templates"
TEMPLATES = {"esp32s3_vscode": "esp32s3_vscode.json", "dht22_uart_example": "dht22_uart_example.cpp"}


def read_template(template_id):
    path = ROOT / TEMPLATES[template_id]
    if any(p.is_symlink() or p.is_junction() for p in [path, ROOT]) or path.stat().st_size > 16000:
        raise ValueError("Invalid template source")
    return path.read_text(encoding="utf-8")


@tool
def load_template(template_id: str = "") -> dict:
    """List/read maintained examples; empty ID lists. esp32s3_vscode contains fixed
    build/serial config; dht22_uart_example is illustrative firmware. Read-only.
    Use scaffold_project to instantiate fixed configuration, not hand-written copies.
    """
    if not template_id:
        return {"execution_status": "ok", "data": {"templates": list(TEMPLATES)}}
    if template_id not in TEMPLATES:
        return {"execution_status": "error", "error_code": "NOT_FOUND", "data": {"templates": list(TEMPLATES)}}
    try:
        content = read_template(template_id)
        return {"execution_status": "ok", "data": {"template_id": template_id, "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest()}}
    except (OSError, ValueError):
        return {"execution_status": "error", "error_code": "INVALID_TEMPLATE", "data": None}
