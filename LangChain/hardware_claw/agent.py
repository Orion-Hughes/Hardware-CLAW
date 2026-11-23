"""Command-line adapter for the Hardware-CLAW coordinator."""
import argparse
import asyncio
import os

from .api_config import ApiConfigError, create_model
from .coordinator import Coordinator, TaskStore, WorkflowError
from .projects.service import ProjectError, ProjectService


async def run(model, question, coordinator):
    from .runtime import execute_turn

    async def emit(kind, data):
        if kind == 'tool_request':
            print(f"[tool request] {data['name']} {data['args']} id={data['id']}")
        elif kind == 'tool_result':
            print(f"[tool result] id={data['id']} {data['content']}")
        elif kind in ('model', 'error', 'host_export'):
            print(f"[{kind}] {data['text']}")
        elif kind in ('stage_start', 'stage_summary'):
            print(f"[{kind}] {data}")
        elif kind == 'summary':
            print(f"[result] {data['status']}; not a hardware validation result")
            print(f"[elapsed] {data['elapsed_seconds']}s")
            print(f"[usage reported by provider] {data['usage'] or 'unavailable'}")
            print(f"[model responses] {data['model_responses']}; main={data['main_model_responses']}")
            if data.get('project'):
                print(f"[project] {data['project']}")

    status = await execute_turn(model, question, [], emit, coordinator=coordinator)
    return 0 if status == 'completed' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ask-key', action='store_true', help='Read key without echo or persistence')
    parser.add_argument('--question', required=True, help='Request for the main coordinator')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--project', metavar='ID', help='Bind an existing workspace project to a new task')
    group.add_argument('--task', metavar='ID', help='Resume an existing coordinator task')
    args = parser.parse_args()
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    try:
        model = create_model(ask_key=args.ask_key)
        store = TaskStore()
        bound = store.load(args.task)['project_id'] if args.task else args.project
        project = ProjectService.open(bound) if bound else None
        task_id = args.task or store.create(project.id if project else None)
        print(f'[task] {task_id}')
        if project:
            print(f'[project bound] {project.id}')
        return asyncio.run(run(model, args.question, Coordinator(task_id, store=store, project=project, builtin_stages=True)))
    except ApiConfigError as exc:
        print(f'[configuration] {exc}')
        return 2
    except (WorkflowError, ProjectError) as exc:
        print(f'[stopped] {exc.code}: {exc}')
        return 2
    except Exception as exc:
        print(f'[stopped] {type(exc).__name__}; check model access, API balance and network.')
        return 1
