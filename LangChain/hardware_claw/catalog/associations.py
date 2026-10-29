"""Resolve thin source bindings into the existing project-facing record contract."""
from .service import CatalogError, _require, IDENTIFIER


def properties(text):
    return dict(line.split('=', 1) for raw in text.splitlines()
                if (line := raw.strip()) and not line.startswith('#') and '=' in line)


def resolve(catalog, association):
    a = association
    _require(isinstance(a.get('driver_ids'), list))
    _require(isinstance(a.get('document_refs'), list) and isinstance(a.get('platform_api_refs'), list))
    _require(isinstance(a.get('compatibility'), dict) and isinstance(a.get('simulation'), dict))
    _require(isinstance(a.get('required_headers'), list))
    _require(all(isinstance(x, str) for x in a['document_refs'] + a['platform_api_refs'] + a['required_headers']))
    source_refs = list(dict.fromkeys(a['document_refs'] + a['platform_api_refs']))
    examples, dependencies, driver_sources, library_metadata = [], [], [], []
    for ident in a['driver_ids']:
        _require(isinstance(ident, str) and bool(IDENTIFIER.fullmatch(ident)))
        descriptor, provenance = catalog._json('drivers/' + ident + '.json', prefixes=('drivers/',))
        _require(descriptor.get('id') == ident)
        prop_ref = descriptor.get('properties_ref')
        _require(isinstance(prop_ref, str))
        try:
            prop = properties(catalog._bytes(prop_ref, prefixes=('upstream/', 'supplements/sources/')).decode('utf-8-sig'))
        except UnicodeError:
            raise CatalogError('INVALID_TEXT', '库清单不是UTF-8。') from None
        _require(bool(prop.get('name')) and bool(prop.get('version')), '上游库清单缺少name/version。')
        dependencies.append({'name': prop['name'], 'version': prop['version'], 'source_ref': prop_ref})
        library_metadata.append({k: prop.get(k) for k in ('name', 'version', 'author', 'maintainer', 'architectures', 'depends', 'url')})
        for field in ('api_refs', 'example_refs'):
            _require(isinstance(descriptor.get(field), list) and all(isinstance(x, str) for x in descriptor[field]))
        source_refs.extend([prop_ref, *descriptor['api_refs']])
        examples.extend(descriptor['example_refs'])
        driver_sources.append(provenance)
    # Ensure every exported path belongs to the local source manifest before the model sees it.
    for ref in dict.fromkeys(source_refs + examples):
        catalog.source_metadata(ref)
    sim = dict(a['simulation'])
    part = sim.get('part_type') or sim.get('candidate_part_type')
    sim.update(backend='wokwi', upstream_definition_ref='upstream/wokwi-diagram-lint/parts/'+part+'.json' if part else None,
               simulation_test='not_run', hardware_test='not_run', mapping_scope='simulation_signals_not_physical_connector_order')
    status = a.get('generation_status')
    _require(status in {'documented_not_tested', 'blocked', 'unreviewed'})
    profile = {
        'schema_version': 1 if status == 'unreviewed' else 2, 'source_schema_version': 3,
        **{k: a[k] for k in ('id', 'name', 'kind', 'inventory', 'record_role')},
        'simulation': sim, 'physical_connector_order': None,
        'electrical_profile': {'scope': 'simulation_connection_policy_only', 'supply_v': a.get('simulation_supply_v'),
                               'logic_v': None, 'source_refs': a['document_refs']},
        'driver_profile': {
            'scope': a['compatibility']['scope'], 'framework': a['compatibility']['framework'],
            'dependencies': dependencies, 'headers': a['required_headers'],
            'api_format': 'upstream_original_documents',
            'framework_api_refs': list(dict.fromkeys(a['platform_api_refs'])),
            'implementation_modes': ['catalog', 'framework'] if a['platform_api_refs'] else ['catalog'],
            'source_refs': list(dict.fromkeys(source_refs)), 'example_refs': list(dict.fromkeys(examples)),
            'upstream_library_metadata': library_metadata, 'descriptor_provenance': driver_sources,
            'instruction': '没有手写API摘要；编写前按需读取已登记原文。architectures=*不证明当前平台运行通过。',
        },
        'documentation_status': 'upstream_snapshots_with_local_bindings_not_runtime_qualified',
        'source_refs': list(dict.fromkeys(source_refs)), 'missing_information': a.get('unknowns', []),
        'notes': ['本条目由关联配置与上游原文派生；电源值仅为仿真连接选择，不是实物额定值。',
                  '库名和版本从原始library.properties读取；器件组合及实际运行仍需验证。'],
    }
    if status != 'unreviewed':
        profile['generation_profile'] = {
            'status': status, 'blockers': a.get('blockers', []),
            'target': 'wokwi', 'build_profile_ref': a['compatibility']['platform_ref'],
            'controls': a.get('controls', []), 'source_refs': a['document_refs'],
        }
    if a.get('physical_display'):
        profile['physical_display'] = a['physical_display']
    return profile
