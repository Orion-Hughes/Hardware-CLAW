"""Small FTA-style handoffs: requirements -> scenarios -> timed input/observation events."""
from typing import Any, Literal
from pydantic import Field
from ..coordinator.contracts import StrictModel


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
    events: list[Event] = Field(min_length=1, max_length=24)


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
    from .simulation_mcp import MCPAction, InspectSimulationInput
    if value.test_id != scenario.test_id or set(value.requirement_ids) != set(scenario.requirement_ids):
        raise ValueError('test_id/requirement_ids必须与当前场景一致')
    actions, observations, previous = [], [], 0
    errors = []
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
        actions.append(MCPAction(operation=binding['operation'], arguments=args))
    if not observations:
        errors.append('至少需要一个read采证事件；设置输入的回执不是功能证据')
    if errors:
        raise ValueError('\n'.join(errors))
    remaining = value.duration_ms - previous
    while remaining:
        wait = min(remaining,10000)
        actions.append(MCPAction(operation='wait', arguments={'milliseconds':wait}))
        remaining -= wait
    if len(actions) > 32:
        waits = sum(a.operation == 'wait' for a in actions)
        raise ValueError(f'转换后共{len(actions)}操作（{len(actions)-waits}个事件+{waits}个等待），上限32。'
                         '正时间差会额外插入wait，末尾duration_ms也可能插入wait。'
                         '请减少冗余采样，或将无需间隔的多个读取安排在同一at_ms；保留场景必要的输入与观察。')
    validated = InspectSimulationInput(expected_version=0, actions=actions)
    return {'test_id':scenario.test_id, 'expected_observable':scenario.expected_observable,
            'requirement_ids':scenario.requirement_ids, 'actions':[a.model_dump() for a in validated.actions],
            'observations':observations, 'time_basis':'host_wall_schedule_not_simulation_time',
            'session':'independent; host starts/closes if executed later', 'execution_performed':False}
