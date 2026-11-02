"""Run one installed child without invoking the main LLM."""
import argparse
import asyncio
import json

from ..api_config import create_model
from ..coordinator import Coordinator, TaskStore
from .selection import attach_selection
from .generation import attach_generation
from ..projects.service import ProjectService
from .. import limits


async def run(question, stage='selection', task_id=None):
    store = TaskStore()
    project = None
    if task_id:
        state = store.load(task_id)
        if state['project_id']: project = ProjectService.open(state['project_id'])
    c = Coordinator(task_id or store.create(), store=store, project=project)
    c.begin_turn(question)
    async def emit(kind, data):
        print(f'[{kind}] ' + json.dumps(data, ensure_ascii=False), flush=True)
    model = create_model(max_tokens=limits.PROJECT_OUTPUT_TOKENS if stage == 'generation' else limits.QUERY_OUTPUT_TOKENS)
    (attach_generation if stage == 'generation' else attach_selection)(c, model, emit)
    result = await c.run_stage(stage, question, c.state()['version'],
        expected_project_version=project.get()['version'] if project and stage == 'generation' else None)
    print('[result] ' + json.dumps(result, ensure_ascii=False), flush=True)
    print('[task] ' + c.task_id, flush=True)
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question', required=True)
    parser.add_argument('--stage', choices=['selection','generation'], default='selection')
    parser.add_argument('--task', help='Resume existing task; generation requires an accepted selection')
    args = parser.parse_args()
    if args.stage == 'generation' and not args.task: parser.error('generation requires --task with an accepted selection')
    raise SystemExit(asyncio.run(run(args.question, args.stage, args.task)))
