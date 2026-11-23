"""Read-only deployment commands for the existing chat frontend."""
import asyncio
import json

from ..projects.service import ProjectError
from ..catalog.service import CatalogError
from .service import list_ports, prepare_upload


async def preview_command(question, project):
    parts = question.split()
    if parts[0] == "/ports":
        if len(parts) != 1:
            return "用法：`/ports`。只枚举系统串口，不连接或复位开发板。"
        try:
            ports = await asyncio.to_thread(list_ports)
            return "系统串口（仅枚举，未连接硬件）：\n```json\n" + json.dumps(ports, ensure_ascii=False, indent=2) + "\n```"
        except ProjectError as exc:
            return f"{exc.code}：{exc}"
    if len(parts) != 1:
        return "用法：`/flash-plan`，为当前绑定工程准备预览。完整操作请点击顶部“固件烧录”，在独立页面选择工程、串口并确认。"
    if project is None:
        return "请点击顶部“固件烧录”直接选择工程文件夹；也可以先用 `/project 工程ID` 绑定工程，再输入 `/flash-plan` 预览。"
    try:
        def prepare():
            return prepare_upload(project, project.get()["version"])
        plan = await asyncio.to_thread(prepare)
        return (f"已生成烧录预览 `{plan['plan_id']}`，工程版本 {plan['version']}。\n\n"
                f"目标配置：`{plan['profile']['board']}`，{plan['profile']['flash_size']} Flash；"
                f"{len(plan['images'])} 个镜像。\n\n"
                + "\n".join("- " + item for item in plan["blockers"])
                + f"\n\n记录：`{plan['plan_path']}`。\n\n未烧录、未打开串口，也未调用 LLM。"
                "完整操作请点击顶部“固件烧录”，选择串口、核对实物并进行二次确认。")
    except (ProjectError, CatalogError) as exc:
        return (f"{exc.code}：{exc}\n\n未烧录。请点击顶部“固件烧录”，选择该工程并勾选"
                "“准备前重新检查并编译”，再点击准备按钮。编译和预览不会写入开发板。")
