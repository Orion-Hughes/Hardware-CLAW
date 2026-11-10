"""Validated host-managed driver bundles; never model-authored project files."""
import hashlib
import json
from pathlib import PurePosixPath

from .service import CatalogError


def _safe_relative(value, field):
    if not isinstance(value, str) or not value:
        raise CatalogError('INVALID_DRIVER_BUNDLE', f'驱动包{field}不能为空。')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or '\\' in value:
        raise CatalogError('INVALID_DRIVER_BUNDLE', f'驱动包{field}不是安全相对路径。')
    return path


def load_bundle(catalog, manifest_ref):
    """Load and validate one local bundle without executing or rewriting it."""
    raw = catalog._bytes(manifest_ref, prefixes=('drivers/',))
    try:
        value = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, ValueError, RecursionError):
        raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包清单不是有效JSON。') from None
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包清单版本不支持。')
    name, version = value.get('library_name'), value.get('version')
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包缺少库名或版本。')
    bundle_ref = str(PurePosixPath(manifest_ref).parent)
    if value.get('install') != {'destination': f'lib/{PurePosixPath(bundle_ref).name}',
                                'managed_by': 'host', 'platformio_lib_deps': False}:
        raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包安装方式必须是宿主注入且不写入lib_deps。')
    entries = value.get('files')
    if not isinstance(entries, list) or not entries or len(entries) > 80:
        raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包文件清单必须为1–80个文件。')
    files, refs = [], []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('path'), str) or not isinstance(entry.get('role'), str):
            raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包文件条目缺少path或role。')
        relative = _safe_relative(entry['path'], '文件路径')
        if relative.as_posix() in {item['path'] for item in files}:
            raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包文件清单存在重复路径。')
        ref = f'{bundle_ref}/{relative.as_posix()}'
        data = catalog._bytes(ref, prefixes=('drivers/',))
        files.append({'path': relative.as_posix(), 'role': entry['role'],
                      'ref': ref, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
        refs.append(ref)
    # Every bundle needs a compilable text entry; the exact language is validated by the real compiler.
    if not any(item['role'] == 'source' for item in files):
        raise CatalogError('INVALID_DRIVER_BUNDLE', '驱动包缺少role=source文件。')
    return {'manifest_ref': manifest_ref, 'bundle_ref': bundle_ref, 'library_name': name,
            'version': version, 'origin': value.get('origin'), 'install': value['install'],
            'files': files, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'all_refs': [manifest_ref, *refs]}


def project_driver_bundles(state):
    """Resolve unique local bundles required by a saved project design."""
    bundles, by_identity, by_destination = [], {}, {}
    for instance, info in (state.get('hardware') or {}).items():
        dependencies = ((info.get('profile') or {}).get('driver_profile') or {}).get('dependencies', [])
        for dependency in dependencies:
            if dependency.get('resolution') != 'local_bundle':
                continue
            from ..catalog import KnowledgeCatalog
            bundle = load_bundle(KnowledgeCatalog(), dependency['bundle_manifest_ref'])
            if bundle['library_name'] != dependency['name'] or bundle['version'] != dependency['version']:
                raise CatalogError('DRIVER_BUNDLE_MISMATCH', f'{instance}的驱动包版本与清单不一致。')
            if bundle['bundle_ref'] != dependency.get('bundle_ref'):
                raise CatalogError('DRIVER_BUNDLE_MISMATCH', f'{instance}的驱动包路径与清单不一致。')
            identity = (bundle['library_name'], bundle['version'], bundle['bundle_ref'])
            if identity not in by_identity:
                by_identity[identity] = bundle
                destination = bundle['install']['destination']
                if destination in by_destination:
                    raise CatalogError('DRIVER_BUNDLE_CONFLICT', f'本地驱动包目标目录冲突：{destination}。')
                by_destination[destination] = bundle
                bundles.append(bundle)
    return bundles


def bundle_bytes(bundle):
    """Return exact manifest and listed source bytes keyed by delivery destination."""
    from ..catalog import KnowledgeCatalog
    catalog = KnowledgeCatalog()
    output = {f'{bundle["install"]["destination"]}/bundle.json':
              catalog._bytes(bundle['manifest_ref'], prefixes=('drivers/',))}
    for item in bundle['files']:
        output[f'{bundle["install"]["destination"]}/{item["path"]}'] = (
            catalog._bytes(item['ref'], prefixes=('drivers/',)))
    return output
