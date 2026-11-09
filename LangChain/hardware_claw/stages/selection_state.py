"""Host-owned selection evidence. Reuse facts, never treat old prose as validation."""
import hashlib
from copy import deepcopy

from ..catalog import KnowledgeCatalog, CatalogError
from ..coordinator.store import WorkflowError

PREFIXES = ('cards/', 'platforms/', 'upstream/', 'guidance/', 'drivers/', 'catalog.json')


def digest(catalog, ref):
    return hashlib.sha256(catalog._bytes(ref, prefixes=PREFIXES)).hexdigest()


class SelectionEvidence:
    def __init__(self, catalog=None):
        self.catalog = catalog or KnowledgeCatalog()
        self.items, self.hashes, self.refs, self.platforms = {}, {}, {}, {}

    def observe(self, data):
        for item in data.get('hardware', []):
            ident = item['id']
            refs = self.refs.setdefault(ident, set())
            if 'simulation' in item:
                self.items[ident] = deepcopy(item)
            for entry in item.get('provenance', {}).values():
                if isinstance(entry, dict) and entry.get('ref') and entry.get('sha256'):
                    self.hashes[entry['ref']] = entry['sha256']
                    if entry['ref'] != 'catalog.json':
                        refs.add(entry['ref'])
            # These properties were parsed by the catalog, even if API source text was not loaded.
            programming = item.get('programming', {})
            for entry in programming.get('dependencies', []) + programming.get('declared_dependencies', []):
                dependency_refs = [entry.get('source_ref'), entry.get('bundle_manifest_ref')]
                dependency_refs.extend(entry.get('bundle_files', []))
                for ref in dependency_refs:
                    if not ref:
                        continue
                    self.hashes[ref] = digest(self.catalog, ref)
                    refs.add(ref)
        for document in data.get('documents', []):
            if not isinstance(document, dict) or document.get('status') != 'included':
                continue
            ref = document['ref']
            self.hashes[ref] = document['sha256']
            for ident in document.get('hardware_ids', []):
                self.refs.setdefault(ident, set()).add(ref)
        for platform in data.get('platforms', []):
            self.platforms[platform['ref']] = deepcopy(platform)
            self.hashes[platform['ref']] = platform['sha256']

    def dump(self, ids):
        ids = set(ids)
        refs = {r for ident in ids for r in self.refs.get(ident, ())}
        return {'schema_version': 1, 'items': {k: v for k, v in self.items.items() if k in ids},
            'hashes': {r: h for r, h in self.hashes.items() if r in refs},
            'refs': {k: sorted(v) for k, v in self.refs.items() if k in ids},
            'platforms': {r: p for r, p in self.platforms.items() if r in refs}}


def accepted_baseline(coordinator, catalog=None):
    """Only the current accepted handoff in this task is eligible, never supplied refs."""
    evidence = SelectionEvidence(catalog)
    ref = coordinator.store.load(coordinator.task_id)['latest'].get('selection')
    result = {'handoff_ref': ref, 'previous': {}, 'reusable_ids': [], 'invalidated': [], 'hardware': [], 'platforms': []}
    if not ref:
        return evidence, result
    handoff = coordinator.store.record(coordinator.task_id, ref)
    if handoff.get('stage') != 'selection' or handoff.get('status') != 'completed':
        raise WorkflowError('INVALID_BASELINE', '当前选型指针不是已接受的选型交接。')
    previous = handoff['result']
    result['previous'] = {k: previous.get(k, []) for k in ('requirements', 'hardware_ids', 'decisions', 'assumptions')}
    ids = previous.get('hardware_ids', [])
    try:
        detail = coordinator.store.record(coordinator.task_id, previous.get('detail_ref'))
        if (detail.get('kind') != 'selection_detail' or detail.get('stage_run_id') != ref
                or detail.get('result', {}).get('status') != 'completed'
                or detail['result'].get('hardware_ids') != ids):
            raise WorkflowError('INVALID_BASELINE', '详细证据与已接受交接不一致。')
    except WorkflowError:
        result['invalidated'] = [{'hardware_id': i, 'reason': 'missing_trusted_evidence'} for i in ids]
        return evidence, result
    snapshot = detail.get('selection_snapshot')
    if snapshot is None:
        # Upgrade old records in memory; preserve originals. Require metadata equality
        # for parsed dependency data whose byte hashes were not stored by the old version.
        for event in detail.get('events', []):
            data = (event.get('result') or {}).get('data') if isinstance(event.get('result'), dict) else None
            if event.get('kind') == 'tool' and event.get('name') == 'read_hardware' and data:
                try:
                    evidence.observe(data)
                except CatalogError:
                    pass
        snapshot = evidence.dump(ids)
        for ident in ids:
            try:
                old = snapshot['items'][ident]
                current = evidence.catalog.get(ident)['profile']['driver_profile']
                current = {k: v for k, v in current.items() if k not in {'source_refs', 'example_refs'}}
                if current != old['programming']:
                    snapshot['items'].pop(ident)
            except (CatalogError, KeyError, TypeError):
                snapshot['items'].pop(ident, None)
    evidence = SelectionEvidence(catalog)
    if snapshot.get('schema_version') != 1:
        result['invalidated'] = [{'hardware_id': i, 'reason': 'unsupported_snapshot'} for i in ids]
        return evidence, result
    fresh = {}
    for path, expected in snapshot.get('hashes', {}).items():
        try:
            fresh[path] = digest(evidence.catalog, path) == expected
        except CatalogError:
            fresh[path] = False
    # Catalog additions do not invalidate unrelated existing cards; remaps/removals do.
    catalog_data, _ = evidence.catalog._json('catalog.json', prefixes=('catalog.json',))
    registered = {r['id']: r for r in catalog_data['records']}
    for ident in ids:
        item = snapshot.get('items', {}).get(ident)
        refs = set(snapshot.get('refs', {}).get(ident, []))
        changed = sorted(p for p in refs if not fresh.get(p, False))
        entry = registered.get(ident, {})
        valid_record = (item and entry.get('path') == item.get('provenance', {}).get('record', {}).get('ref')
                        and entry.get('owned') == item['summary'].get('owned'))
        if valid_record and item['simulation'].get('part_type'):
            valid_record = (catalog_data.get('upstream_parts', {}).get(item['simulation']['part_type'])
                            == item.get('provenance', {}).get('upstream_definition', {}).get('ref'))
        if not item or not refs or changed or not valid_record:
            result['invalidated'].append({'hardware_id': ident, 'reason': 'source_changed_or_missing', 'references': changed})
            continue
        evidence.items[ident] = deepcopy(item)
        evidence.refs[ident] = refs
    kept = {r for refs in evidence.refs.values() for r in refs}
    evidence.hashes = {r: h for r, h in snapshot['hashes'].items() if r in kept}
    evidence.platforms = {r: p for r, p in snapshot.get('platforms', {}).items() if r in kept and fresh.get(r)}
    result['reusable_ids'] = list(evidence.items)
    result['source_refs'] = sorted(evidence.hashes)
    result['hardware'] = [compact_item(item) for item in evidence.items.values()]
    result['platforms'] = [compact_platform(p) for p in evidence.platforms.values()]
    return evidence, result


def compact_item(item):
    summary = item['summary']
    return {'id': item['id'], 'name': summary['name'], 'kind': summary['kind'],
        'owned': summary.get('owned'), 'record_role': summary.get('record_role'),
        'selection': summary.get('selection'), 'availability': item['availability'],
        'simulation': item['simulation'], 'programming': item['programming'],
        'electrical': item['electrical'], 'platform_ref': item.get('platform_ref')}


def compact_platform(platform):
    content = platform['content']
    return {'ref': platform['ref'], 'content': {k: content[k] for k in ('scope', 'build', 'gpio_policy', 'policy') if k in content}}
