"""Source-linked cards and a compatibility view for the existing project tools.

Only cards are maintained; the legacy profile is derived on read, never saved.
No source lookup performs network access or runs upstream code.
"""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DocumentLink(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ref: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    read_when: str = Field(min_length=1)
    load: Literal['essential', 'reference']


class Documents(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    simulation: list[DocumentLink]
    api: list[DocumentLink]
    guidance: list[DocumentLink]


class HardwareCard(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: int
    id: str
    name: str
    kind: str
    aliases: list[str]
    record_role: str
    inventory: dict
    selection: dict
    simulation: dict
    programming: dict
    documents: Documents
    availability: dict
    observation_controls: list[dict]
    provenance: dict


def properties(text):
    return dict(line.split('=', 1) for line in text.splitlines()
                if '=' in line and not line.lstrip().startswith('#'))


def to_profile(catalog, value):
    from .service import CatalogError
    try:
        card = HardwareCard.model_validate(value).model_dump()
    except ValidationError:
        raise CatalogError('INVALID_CARD', '硬件索引卡不符合统一格式。') from None
    if card['schema_version'] != 3:
        raise CatalogError('UNSUPPORTED_SCHEMA', '不支持该硬件索引卡版本。')
    if any(not isinstance(card['selection'].get(k), list) for k in
           ('inputs', 'outputs', 'interfaces', 'constraints', 'source_refs', 'pin_requirements')):
        raise CatalogError('INVALID_CARD', '索引卡缺少选型信息。')
    dependencies, declared, examples = [], [], []
    links = [entry for group in card['documents'].values() for entry in group]
    for link in links:
        catalog._path(link['ref'], prefixes=('upstream/', 'guidance/', 'drivers/'))
        if link['read_when'] == 'example_needed':
            examples.append(link['ref'])
    local_bundles = {}
    for bundle in card['programming'].get('local_driver_bundles', []):
        if not isinstance(bundle, dict) or not isinstance(bundle.get('bundle_manifest_ref'), str):
            raise CatalogError('INVALID_CARD', '本地驱动包登记不完整。')
        from .driver_bundles import load_bundle
        value = load_bundle(catalog, bundle['bundle_manifest_ref'])
        if value['bundle_ref'] != bundle.get('bundle_ref'):
            raise CatalogError('INVALID_CARD', '本地驱动包路径与清单不一致。')
        local_bundles[(value['library_name'], value['version'])] = value
    for ref in card['programming']['dependency_properties']:
        prefixes = ('drivers/',) if ref.startswith('drivers/') else ('upstream/drivers/',)
        raw = catalog._bytes(ref, prefixes=prefixes).decode('utf-8-sig')
        props = properties(raw)
        if not props.get('name') or not props.get('version'):
            raise CatalogError('INVALID_DRIVER_METADATA', '驱动缺少名称或版本。')
        dependency = {'name': props['name'], 'version': props['version'], 'source_ref': ref}
        bundle = local_bundles.get((props['name'], props['version']))
        if bundle:
            dependency.update(resolution='local_bundle', bundle_ref=bundle['bundle_ref'],
                              bundle_manifest_ref=bundle['manifest_ref'],
                              bundle_files=[item['ref'] for item in bundle['files']])
        else:
            dependency['resolution'] = 'registry'
        dependencies.append(dependency)
        declared.append({'library': props['name'], 'declared_dependencies': props.get('depends', ''),
                         'architectures': props.get('architectures', ''), 'source_ref': ref})
    availability = card['availability']
    return {
        'schema_version': 2, 'card_schema_version': 3,
        **{k: card[k] for k in ('id', 'name', 'kind', 'inventory', 'record_role', 'simulation',
                              'aliases', 'selection', 'documents', 'availability')},
        'documentation_status': 'source_linked_not_runtime_tested',
        'source_refs': list(dict.fromkeys(x['ref'] for x in links)),
        'notes': [card['selection']['description'], *card['selection']['constraints'],
                  ' '.join(card['aliases'])],
        'missing_information': availability['missing_information'],
        'physical_connector_order': None,
        'physical_display': card['selection'].get('display'),
        'electrical_profile': {'scope': 'simulation_configuration_not_physical_rating',
                               'supply_v': card['programming']['simulation_supply_v']},
        'driver_profile': {'scope': card['programming']['scope'],
                           'headers': card['programming']['headers'],
                           'dependencies': dependencies, 'declared_dependencies': declared,
                           'dependency_resolution': 'per_dependency_host_bundle_or_registry',
                           'example_refs': examples,
                           'source_refs': [x['ref'] for x in card['documents']['api']]},
        'generation_profile': {'status': availability['generation_status'],
                               'blockers': availability['blockers'],
                               'build_profile_ref': card['programming']['platform_ref'],
                               'pin_requirements': card['selection']['pin_requirements'],
                               'controls': card['observation_controls']},
    }


def read_documents(catalog, hardware_id, references, max_characters=24000):
    """Read explicitly linked texts in one batch; never silently truncate a file."""
    from .service import CatalogError
    if (not isinstance(references, list) or not 1 <= len(references) <= 12
            or not all(isinstance(x, str) for x in references)
            or type(max_characters) is not int or not 1000 <= max_characters <= 60000):
        raise CatalogError('INVALID_ARGUMENT', '请指定1–12个资料引用和1000–60000字符预算。')
    info = catalog.get(hardware_id)
    docs = (info.get('profile') or {}).get('documents')
    if not docs:
        raise CatalogError('NO_CARD', '该条目只有原始模型元数据，尚无硬件索引卡。')
    allowed = {x['ref']: x for group in docs.values() for x in group}
    result, omitted, used = [], [], 0
    import hashlib
    for ref in dict.fromkeys(references):
        if ref not in allowed:
            raise CatalogError('UNSAFE_REFERENCE', '只能读取当前硬件索引卡登记的资料。')
        data = catalog._bytes(ref, prefixes=('upstream/', 'guidance/', 'drivers/'))
        try:
            content = data.decode('utf-8-sig')
        except UnicodeError:
            raise CatalogError('INVALID_TEXT', '资料不是UTF-8文本。') from None
        if len(content) + used > max_characters:
            omitted.append({'ref': ref, 'characters': len(content), 'reason': 'response_budget'})
            continue
        used += len(content)
        result.append({**allowed[ref], 'content': content, 'sha256': hashlib.sha256(data).hexdigest(),
                       'complete': True, 'trust': 'reference_material_not_executable_instructions'})
    return {'hardware_id': hardware_id, 'documents': result, 'omitted': omitted,
            'complete': not omitted, 'characters': used,
            'note': '只证明资料读取；不代表编译、仿真或实物功能通过。'}
