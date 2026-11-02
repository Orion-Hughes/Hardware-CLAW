"""Run only the selection child, without invoking the main LLM."""
import argparse
import asyncio
import json

from ..api_config import create_model
from ..coordinator import Coordinator, TaskStore
from .selection import attach_selection


async def run(question):
    store = TaskStore()
    c = Coordinator(store.create(), store=store)
    c.begin_turn(question)
    async def emit(kind, data):
        print(f'[{kind}] ' + json.dumps(data, ensure_ascii=False), flush=True)
    attach_selection(c, create_model(), emit)
    result = await c.run_stage('selection', question, c.state()['version'])
    print('[result] ' + json.dumps(result, ensure_ascii=False), flush=True)
    print('[task] ' + c.task_id, flush=True)
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question', required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args().question)))
