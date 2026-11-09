"""Derived wiring inventory, not a firmware pin-mode or electrical verifier."""
import hashlib
import json
import re

from ..catalog import KnowledgeCatalog, CatalogError
from ..validation.files import strict_json


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_gpio_map(state, catalog=None):
    """Read the saved diagram and source-backed board aliases. Never infer chip wiring."""
    catalog = catalog or KnowledgeCatalog()
    text = state.get('files', {}).get('diagram.json')
    design, hardware = state.get('design') or {}, state.get('hardware', {})
    report = {
        'schema_version': 1, 'project_id': state['project_id'], 'version': state['version'],
        'design_version': state.get('design_version'), 'status': 'unavailable',
        'scope': 'diagram_wire_connectivity_not_firmware_or_electrical_validation',
        'diagram_sha256': sha(text) if text is not None else None,
        'hardware_snapshot_sha256': sha(json.dumps(hardware, sort_keys=True, ensure_ascii=False)),
        'design_sha256': sha(json.dumps(design, sort_keys=True, ensure_ascii=False)),
        'rows': [], 'unmapped_board_endpoints': [], 'issues': [], 'sources': [],
        'note': '仅列电路中连线的GPIO；不推断器件内部导通、固件模式、频率或上下拉。常量名称来自设计，未核验源码。',
    }

    def issue(code, detail):
        report['issues'].append({'code': code, 'detail': detail})

    if text is None:
        issue('DIAGRAM_REQUIRED', '尚无diagram.json；生成电路后自动整理GPIO表。')
        return report
    try:
        diagram = strict_json(text)
        if not isinstance(diagram, dict) or diagram.get('version') != 1:
            raise ValueError()
        parts = diagram['parts']
        if not isinstance(parts, list):
            raise ValueError()
        actual = {}
        for part in parts:
            if (not isinstance(part, dict) or not isinstance(part.get('id'), str)
                    or not isinstance(part.get('type'), str) or part['id'] in actual):
                raise ValueError()
            actual[part['id']] = part
        edges = diagram['connections']
        if not isinstance(edges, list):
            raise ValueError()
        for edge in edges:
            if (not isinstance(edge, list) or len(edge) != 4
                    or not all(isinstance(x, str) for x in edge[:3])
                    or not isinstance(edge[3], list) or not all(isinstance(x, str) for x in edge[3])
                    or any(':' not in x or not all(x.split(':', 1)) for x in edge[:2])):
                raise ValueError()
    except (ValueError, KeyError, TypeError, RecursionError):
        issue('INVALID_DIAGRAM', '电路JSON或parts/connections格式无效，未生成接线结论。')
        return report

    if set(actual) != set(hardware):
        issue('PART_MISMATCH', '电路器件实例与已保存设计不一致。')
    expected = {tuple(sorted((e['a'], e['b']))) for e in design.get('connections', [])}
    drawn = [tuple(sorted(e[:2])) for e in edges]
    if set(drawn) != expected or len(drawn) != len(set(drawn)):
        issue('CONNECTION_MISMATCH', '电路与设计连接不一致或含重复连线；表格按电路实际连线生成。')
    if state.get('files_design_version') != state.get('design_version'):
        issue('STALE_DESIGN', '当前文件未对应最新设计版本。')

    parent = {}
    def find(node):
        parent.setdefault(node, node)
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != node:
            old = parent[node]
            parent[node] = root
            node = old
        return root

    known_endpoints = {'$serialMonitor:TX', '$serialMonitor:RX'}
    trusted = {}
    for ident, part in actual.items():
        info = hardware.get(ident)
        if not info or part['type'] != info['upstream_definition']['type']:
            issue('UNMAPPED_PART', f'{ident}型号未在当前设计中对应，保留端点但不推断功能。')
            continue
        trusted[ident] = info
        known_endpoints.update(f'{ident}:{pin}' for pin in info['upstream_definition']['pins'])
    for a, b, *_ in edges:
        parent[find(a)] = find(b)
        for endpoint in (a, b):
            if endpoint not in known_endpoints:
                issue('UNKNOWN_ENDPOINT', endpoint)
    nets = {}
    for endpoint in parent:
        nets.setdefault(find(endpoint), []).append(endpoint)

    def destination(endpoint):
        ident, pin = endpoint.split(':', 1)
        info = trusted.get(ident, {})
        profile = info.get('profile') or {}
        signals = profile.get('simulation', {}).get('logical_signal_to_model_pin', {})
        return {'endpoint': endpoint, 'hardware_id': info.get('summary', {}).get('id'),
                'part_type': actual.get(ident, {}).get('type'),
                'signals': sorted(k for k, v in signals.items() if v == pin)}

    boards_found = 0
    for ident, info in trusted.items():
        if info['summary']['kind'] != 'board':
            continue
        boards_found += 1
        profile = info.get('profile') or {}
        refs = sorted({ref for ref in profile.get('source_refs', [])
                       if ref.startswith('upstream/wokwi-boards/') and ref.endswith('/board.json')})
        targets = {}
        if len(refs) != 1:
            issue('BOARD_MAPPING_UNAVAILABLE', f'{ident}:缺少唯一的上游板卡引脚映射，不能按编号猜测。')
        else:
            try:
                board, provenance = catalog._json(refs[0], prefixes=('upstream/wokwi-boards/',))
                pins = board['pins']
                if not isinstance(pins, dict) or not all(isinstance(v, dict) and isinstance(v.get('target'), str) for v in pins.values()):
                    raise ValueError()
                targets = {pin: value['target'] for pin, value in pins.items()
                           if pin in info['upstream_definition']['pins']}
                report['sources'].append(provenance)
            except (CatalogError, ValueError, KeyError, TypeError) as exc:
                issue(getattr(exc, 'code', 'INVALID_BOARD_MAPPING'), f'{ident}:板卡映射读取失败，不猜测GPIO。')
        groups = {}
        for endpoint in sorted(parent):
            owner, pin = endpoint.split(':', 1)
            if owner != ident:
                continue
            target = targets.get(pin)
            match = re.fullmatch(r'GPIO(\d+)', target or '')
            if not match:
                if target is None:
                    report['unmapped_board_endpoints'].append(endpoint)
                    issue('UNKNOWN_BOARD_PIN', endpoint)
                # Known power/reset terminals are not GPIOs.
                continue
            gpio = int(match[1])
            group = groups.setdefault(gpio, {'pins': [], 'endpoints': set()})
            group['pins'].append(pin)
            group['endpoints'].update(nets[find(endpoint)])
        policy = (info.get('shared_configuration') or {}).get('gpio_policy', {})
        for gpio, group in sorted(groups.items()):
            own = {f'{ident}:{p}' for p in group['pins']}
            peers = sorted(group['endpoints'] - own)
            rules = sorted(k for k, v in policy.items() if isinstance(v, list)
                           and k.startswith(('reserve_', 'avoid_', 'unavailable_')) and gpio in v)
            report['rows'].append({'board_instance': ident, 'gpio': gpio,
                'board_pins': sorted(group['pins']), 'connected_to': [destination(e) for e in peers],
                'pin_defines': sorted(k for k, v in design.get('pin_defines', {}).items() if v == gpio)
                    if ident == 'mcu' else [], 'board_policy_notes': rules})
    if not boards_found:
        issue('BOARD_MAPPING_UNAVAILABLE', '电路中没有与设计匹配的已知主板。')
    report['status'] = 'partial' if report['issues'] else 'ready'
    if not boards_found or (not report['rows'] and report['unmapped_board_endpoints']):
        report['status'] = 'unavailable'
    return report


def render_markdown(report):
    def cell(value):
        return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')
    lines = ['# GPIO 接线表（程序生成）', '',
             f"工程：{cell(report['project_id'])}；版本：{report['version']}；状态：{report['status']}", '',
             report['note'], '', '| 主板 | GPIO | 板端点 | 连接端点与信号 | 设计常量 | 板级限制提示 |',
             '|---|---|---|---|---|---|']
    for row in report['rows']:
        peers = '; '.join(d['endpoint'] + (' (' + ', '.join(d['signals']) + ')' if d['signals'] else '')
                          for d in row['connected_to'])
        fields = [row['board_instance'], row['gpio'], ', '.join(row['board_pins']), peers,
                  ', '.join(row['pin_defines']), ', '.join(row['board_policy_notes'])]
        lines.append('| ' + ' | '.join(cell(v) for v in fields) + ' |')
    if not report['rows']:
        lines.extend(['', '没有可确认映射的已连线 GPIO。'])
    if report['issues']:
        lines.extend(['', '## 缺口与不一致', ''])
        lines.extend(f"- {cell(i['code'])}: {cell(i['detail'])}" for i in report['issues'])
    lines.extend(['', f"diagram SHA256：{report['diagram_sha256']}", '', '## 板卡映射来源', ''])
    lines.extend(f"- {cell(s['ref'])} ({s['sha256']})" for s in report['sources'])
    return '\n'.join(lines) + '\n'
