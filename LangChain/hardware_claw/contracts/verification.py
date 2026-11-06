"""Small FTA-style handoffs: requirements -> scenarios -> timed input/observation events."""
from typing import Any, Literal
from pydantic import Field
from ..coordinator.contracts import StrictModel

TIMELINE_EVENT_LIMIT = 32

class Requirement(StrictModel):
    id: str = Field(pattern=r'^R[1-9][0-9]*$')
    description: str = Field(min_length=1, max_length=1000)
    source_line: int = Field(ge=1)
    threshold: float | None = None
    time_value_ms: int | None = Field(default=None, ge=0)
    ambiguous: bool = False


class Requirements(StrictModel):
    requirements: list[Requirement] = Field(min_length=1, max_length=24)


class Scenario(StrictModel):
    test_id: str = Field(pattern=r'^T[1-9][0-9]*$')
    requirement_ids: list[str] = Field(min_length=1, max_length=24)
    fault_type: Literal['nominal', 'boundary', 'state_transition', 'combined', 'communication']
    channel: str
    reason: str = Field(min_length=1, max_length=1000)
    expected_observable: str = Field(min_length=1, max_length=1500)


class Gap(StrictModel):
    requirement_ids: list[str] = Field(min_length=1, max_length=24)
    reason: str = Field(min_length=1, max_length=1000)


class TestPlan(StrictModel):
    test_plan: list[Scenario] = Field(default_factory=list, max_length=8)
    gaps: list[Gap] = Field(default_factory=list, max_length=24)


class Event(StrictModel):
    at_ms: int = Field(ge=0, le=60000)
    action: Literal['set', 'read', 'write']
    channel: str
    value: Any = None
    expected: str | None = Field(default=None, max_length=1000)


class Timeline(StrictModel):
    test_id: str
    requirement_ids: list[str] = Field(min_length=1, max_length=24)
    duration_ms: int = Field(ge=1, le=60000)
    # Advertise the same contract to the model, but defer count enforcement to
    # compile_timeline so it can report event AND expanded-action limits together.
    events: list[Event] = Field(min_length=1, json_schema_extra={'maxItems':TIMELINE_EVENT_LIMIT})


def check_requirements(value, spec_lines):
    ids = [r.id for r in value.requirements]
    if len(ids) != len(set(ids)):
        raise ValueError('requirement id重复')
    if any(r.source_line > len(spec_lines) for r in value.requirements):
        raise ValueError('source_line超出提供的需求原文行号')


def check_plan(value, requirements, io_map):
    required = {r.id for r in requirements.requirements}
    ids = [s.test_id for s in value.test_plan]
    if len(ids) != len(set(ids)):
        raise ValueError('test_id重复')
    covered = {r for item in [*value.test_plan, *value.gaps] for r in item.requirement_ids}
    if covered != required:
        raise ValueError(f'需求覆盖缺失={sorted(required-covered)}；未知引用={sorted(covered-required)}')
    channels = set(io_map['inputs']) | set(io_map['outputs'])
    for scenario in value.test_plan:
        if scenario.channel not in channels:
            raise ValueError(f'{scenario.test_id}:未知channel={scenario.channel}；可用={sorted(channels)}')


def compile_timeline(value, scenario, io_map):
    """Translate explicit events only. No simulator import, dispatch or behavioral verdict."""
    from .simulation_mcp import MCPAction, InspectSimulationInput, MCP_ACTION_LIMIT
    errors = []
    if value.test_id != scenario.test_id or set(value.requirement_ids) != set(scenario.requirement_ids):
        errors.append('test_id/requirement_ids必须与当前场景一致')
    count = len(value.events)
    if count > TIMELINE_EVENT_LIMIT:
        errors.append(f'events数量为{count}，上限{TIMELINE_EVENT_LIMIT}，至少减少{count-TIMELINE_EVENT_LIMIT}个事件。')
    times = [0, *[event.at_ms for event in value.events], value.duration_ms]
    if all(a <= b for a,b in zip(times,times[1:])):
        waits = sum((b-a+9999)//10000 for a,b in zip(times,times[1:]))
        total = count + waits
        if total > MCP_ACTION_LIMIT:
            errors.append(f'按当前时间表转换后共{total}操作（{count}个事件+{waits}个等待），上限{MCP_ACTION_LIMIT}，'
                f'需至少减少{total-MCP_ACTION_LIMIT}个最终操作。'
                '每个事件占1操作，正时间差每10000ms向上取整增加wait，末尾duration_ms也可能增加wait。'
                '请修改events列表或确实不需要间隔的观察时刻，保留必要刺激、响应等待与采证；'
                '只缩短expected文字不会减少数量。减少事件后等待数也需重新计算。')
    actions, observations, previous = [], [], 0
    for index, event in enumerate(value.events):
        prefix = f'events[{index}]'
        if event.at_ms < previous or event.at_ms > value.duration_ms:
            errors.append(f'{prefix}:at_ms必须有序且不超过duration_ms')
            continue
        delay = event.at_ms - previous
        while delay:
            wait = min(delay, 10000)
            actions.append(MCPAction(operation='wait', arguments={'milliseconds':wait}))
            delay -= wait
        previous = event.at_ms
        table = io_map['outputs'] if event.action == 'read' else io_map['inputs']
        binding = table.get(event.channel)
        if not binding or event.action != binding['action']:
            errors.append(f'{prefix}: {event.action}/{event.channel}不可用；检查io_map')
            continue
        args = dict(binding['arguments'])
        if event.action == 'set':
            import math
            if type(event.value) not in (float,int) or not math.isfinite(event.value):
                errors.append(f'{prefix}:value需要有限数值'); continue
            bounds = binding.get('range')
            if bounds and not bounds[0] <= event.value <= bounds[1]:
                errors.append(f'{prefix}:value超出{bounds}'); continue
            if binding.get('type') == 'int' and not float(event.value).is_integer():
                errors.append(f'{prefix}:value需要整数'); continue
            args['value'] = event.value
        elif event.action == 'write':
            if not isinstance(event.value, str):
                errors.append(f'{prefix}:value需要串口文本'); continue
            args['text'] = event.value
        elif event.value is not None:
            errors.append(f'{prefix}:read不接受value'); continue
        if event.action == 'read':
            if not event.expected or not event.expected.strip():
                errors.append(f'{prefix}:采证read需要expected，说明如何评估和证据限制'); continue
            observations.append({'event_index':index, 'action_index':len(actions),
                                 'channel':event.channel, 'expected':event.expected,
                                 'evaluation':'not_executed; textual criterion requires later evaluation'})
        elif event.expected is not None:
            errors.append(f'{prefix}:expected只用于read采证事件'); continue
        try:
            actions.append(MCPAction(operation=binding['operation'], arguments=args))
        except ValueError as exc:
            errors.append(f'{prefix}:工具参数无效：{exc}')
    if not observations:
        errors.append('至少需要一个read采证事件；设置输入的回执不是功能证据')
    if errors:
        raise ValueError('\n'.join(errors))
    remaining = value.duration_ms - previous
    while remaining:
        wait = min(remaining,10000)
        actions.append(MCPAction(operation='wait', arguments={'milliseconds':wait}))
        remaining -= wait
    validated = InspectSimulationInput(expected_version=0, actions=actions)
    return {'test_id':scenario.test_id, 'expected_observable':scenario.expected_observable,
            'requirement_ids':scenario.requirement_ids, 'actions':[a.model_dump() for a in validated.actions],
            'observations':observations, 'time_basis':'host_wall_schedule_not_simulation_time',
            'session':'independent; host starts/closes if executed later', 'execution_performed':False}
