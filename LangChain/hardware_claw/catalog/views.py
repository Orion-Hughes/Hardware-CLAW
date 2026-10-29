"""Small model-facing projections; original records remain available explicitly."""
from pathlib import PurePosixPath


def api_reference(ref):
    path = PurePosixPath(ref)
    return not ('.github' in path.parts or path.name.lower() in {
        'code-of-conduct.md', 'code_of_conduct.md', 'contributing.md',
        'license', 'license.txt', 'license.md', 'authors', 'keywords.txt',
    })


def compact_driver(driver):
    if not driver:
        return None
    out = {k: driver[k] for k in ('scope', 'framework', 'headers', 'api_format', 'implementation_modes') if k in driver}
    out['dependencies'] = [{k: d[k] for k in ('name', 'version') if k in d}
                           for d in driver.get('dependencies', [])]
    out['details_tool'] = 'get_driver_api'
    if driver.get('framework_api_refs'):
        out['framework_api_hint'] = '选择framework实现前，用get_driver_api(detail=full)取得framework_api_refs并读取所需原文。'
    return out


def compact_hardware(data):
    profile = data.get('profile')
    if not isinstance(profile, dict):
        return data
    profile = {k: v for k, v in profile.items() if k != 'source_refs'}
    profile['driver_profile'] = compact_driver(profile.get('driver_profile'))
    return data | {'profile': profile, 'view': 'compact',
                   'detail_note': '原文入口用get_driver_api；detail=full可读完整资料。状态、未知项及仿真约束未省略。'}
