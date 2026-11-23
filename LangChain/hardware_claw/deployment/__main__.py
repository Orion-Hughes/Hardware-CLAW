"""Human-operated firmware upload CLI. No LLM calls; prepare never flashes."""
import argparse
import asyncio
import json

from ..projects.service import ProjectService, ProjectError
from ..catalog.service import CatalogError
from ..adapters.compiler import compile_project
from .service import list_ports, prepare_upload, execute_upload
from .target import TARGET


async def dispatch(args):
    if args.command == "ports":
        return {"execution_status": "ok", "ports": list_ports(), "serial_opened": False}
    project = ProjectService.open(args.project)
    if args.command == "execute":
        return await execute_upload(project, args.plan, args.confirm)
    version = project.get()["version"]
    if args.rebuild:
        check = project.check_files(version)
        if check["verdict"] != "pass":
            return {"execution_status": "blocked", "error_code": "CHECK_REQUIRED", "check": check}
        build = await compile_project(project, version, target=TARGET)
        if build["verdict"] != "pass":
            return {"execution_status": "blocked", "error_code": "BUILD_FAILED", "build": build}
    return prepare_upload(project, version, port=args.port, board=args.board,
                          hardware_reviewed=args.hardware_reviewed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ports", help="只枚举系统串口，不连接/复位设备")
    prepare = commands.add_parser("prepare", help="准备完整镜像与命令预览，绝不烧录")
    prepare.add_argument("--project", required=True)
    prepare.add_argument("--rebuild", action="store_true", help="显式重新检查编译，不改生成源码")
    prepare.add_argument("--port", help="用户选择的 COM 串口，不指定时只生成不可执行预览")
    prepare.add_argument("--board", help="用户确认的 PlatformIO 板卡 ID")
    prepare.add_argument("--hardware-reviewed", action="store_true",
                         help="已人工核对实物规格、接线和覆盖数据风险")
    execute = commands.add_parser("execute", help="真实烧录；仅供用户显式输入确认码，不自动重试")
    execute.add_argument("--project", required=True)
    execute.add_argument("--plan", required=True)
    execute.add_argument("--confirm", required=True)
    try:
        data = asyncio.run(dispatch(parser.parse_args()))
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 2 if data.get("execution_status") == "blocked" or data.get("status") in {"fail", "timeout", "tool_error", "log_limit"} else 0
    except (ProjectError, CatalogError) as exc:
        print(json.dumps({"execution_status": "error", "error_code": exc.code, "summary": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    except (OSError, ValueError):
        print(json.dumps({"execution_status": "error", "error_code": "UPLOAD_IO_ERROR",
                          "summary": "本地烧录文件或接口异常，请检查本地记录。"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
