"""Run one installed child without invoking the main LLM."""
import argparse
import asyncio
import json

from ..api_config import create_model
from ..coordinator import Coordinator, TaskStore
from .selection import attach_selection
from .generation import attach_generation
from .verification import attach_verification
from ..projects.service import ProjectService
from .. import limits


async def run(question, stage='selection', task_id=None, project_id=None):
    store = TaskStore()
    project = None
    if task_id:
        state = store.load(task_id)
        if state['project_id']: project = ProjectService.open(state['project_id'])
    elif project_id:
        project = ProjectService.open(project_id)
    c = Coordinator(task_id or store.create(project_id=project.id if project else None), store=store, project=project)
    c.begin_turn(question)
    async def emit(kind, data):
        print(f'[{kind}] ' + json.dumps(data, ensure_ascii=False), flush=True)
    model = create_model(max_tokens={'generation':limits.PROJECT_OUTPUT_TOKENS,
        'verification':limits.VERIFICATION_OUTPUT_TOKENS,'selection':limits.QUERY_OUTPUT_TOKENS}[stage])
    {'selection':attach_selection,'generation':attach_generation,'verification':attach_verification}[stage](c, model, emit)
    result = await c.run_stage(stage, question, c.state()['version'],
        expected_project_version=project.get()['version'] if project and stage in ('generation','verification') else None)
    print('[result] ' + json.dumps(result, ensure_ascii=False), flush=True)
    print('[task] ' + c.task_id, flush=True)
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question', required=True)
    parser.add_argument('--stage', choices=['selection','generation','verification'], default='selection')
    parser.add_argument('--task', help='Resume existing task; generation requires an accepted selection')
    parser.add_argument('--project', help='Bind an existing project ID for read-only verification planning')
    args = parser.parse_args()
    if args.stage == 'generation' and not args.task: parser.error('generation requires --task with an accepted selection')
    if args.project and (args.task or args.stage != 'verification'): parser.error('--project only supports verification without --task')
    if args.stage == 'verification' and not (args.project or args.task): parser.error('verification requires --project or --task')
    raise SystemExit(asyncio.run(run(args.question, args.stage, args.task, args.project)))
