"""Hardware-CLAW query and project agents with shared skills and live context."""
import argparse
import asyncio
import os

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from .api_config import ApiConfigError, create_model
from . import limits

from .tools.hardware_catalog import HARDWARE_TOOLS
from .tools.skills import load_skill
from .tools.templates import load_template

from .tools.driver_api import get_driver_api
from .context import GenerationContextMiddleware, system_prompt
from .token_budget import TokenBudgetMiddleware
from .message_view import MessageViewMiddleware


MODEL_CALL_LIMIT = limits.QUERY_MODEL_CALLS
TOOL_CALL_LIMIT = limits.QUERY_TOOL_CALLS
RUN_TIMEOUT_SECONDS = limits.QUERY_TIMEOUT_SECONDS


def build_agent(model, project=None):
    from .tools.project_tools import make_project_tools
    return create_agent(
        model=model,
        tools=[*HARDWARE_TOOLS, get_driver_api, load_skill, load_template, *(make_project_tools(project) if project else [])],
        system_prompt=system_prompt(project is not None),
        middleware=[
            GenerationContextMiddleware(project),
            MessageViewMiddleware(),
            TokenBudgetMiddleware(limits.PROJECT_TOTAL_TOKENS if project else limits.QUERY_TOTAL_TOKENS,
                                  limits.PROJECT_OUTPUT_TOKENS if project else limits.QUERY_OUTPUT_TOKENS),
            ModelCallLimitMiddleware(run_limit=limits.PROJECT_MODEL_CALLS if project else MODEL_CALL_LIMIT, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=limits.PROJECT_TOOL_CALLS if project else TOOL_CALL_LIMIT, exit_behavior="error"),
        ],
    )


async def run(model, question, project=None, require_delivery=False):
    from .runtime import execute_turn

    async def emit(kind, data):
        if kind == "tool_request":
            print(f"[tool request] {data['name']} {data['args']} id={data['id']}")
        elif kind == "tool_result":
            print(f"[tool result] id={data['id']} {data['content']}")
        elif kind in ("model", "error", "host_export"):
            print(f"[{kind}] {data['text']}")
        elif kind == "summary":
            print(f"[result] {data['status']}; not a hardware validation result")
            print(f"[elapsed] {data['elapsed_seconds']}s")
            print(f"[usage reported by provider] {data['usage'] or 'unavailable'}")
            if data.get("project"):
                print(f"[project] {data['project']}")

    status = await execute_turn(model, question, [], emit, project=project, require_delivery=require_delivery)
    return 0 if status == "completed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ask-key", action="store_true", help="Read key without echo or persistence")
    parser.add_argument("--question", default="列出本地可用的开发板与元件，说明资料和验证状态。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--new-project", metavar="NAME", help="Explicitly create a project and generate/export artifacts")
    group.add_argument("--project", metavar="ID", help="Resume an existing workspace project")
    parser.add_argument("--template", choices=["arduino", "platformio", "vscode"], default="vscode")
    parser.add_argument("--require-delivery", action="store_true", help="Fail completion if current artifacts are not checked and exported")
    args = parser.parse_args()
    # No hosted tracing configured by this experiment.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    try:
        from .projects.service import ProjectService
        project = None
        if args.new_project:
            project = ProjectService.create(args.new_project, args.question, args.template)
        elif args.project:
            project = ProjectService.open(args.project)
        if project:
            print(f"[project bound] {project.id}")
        model = create_model(ask_key=args.ask_key, max_tokens=limits.PROJECT_OUTPUT_TOKENS if project else limits.QUERY_OUTPUT_TOKENS)
        question = args.question
        if args.new_project or args.require_delivery:
            question += "\n请实际生成/完善绑定工程，运行基础文件检查并导出；只用已注册工具，未完成则如实说明。"
        return asyncio.run(run(model, question, project, bool(args.new_project or args.require_delivery)))
    except ApiConfigError as exc:
        print(f"[configuration] {exc}")
        return 2
    except Exception as exc:
        # Avoid dumping request headers, credentials or raw SDK error bodies.
        print(f"[stopped] {type(exc).__name__}; check model access, API balance and network.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
