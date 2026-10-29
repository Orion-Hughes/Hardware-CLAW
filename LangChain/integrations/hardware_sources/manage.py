"""Verify or restore source bytes from the pinned manifest; never run during Agent tasks."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import urllib.request


def target_path(root, ref):
    parts = PurePosixPath(ref)
    if not ref.startswith(('upstream/', 'supplements/sources/')) or '\\' in ref or ':' in ref or '..' in parts.parts:
        raise ValueError('Invalid source reference')
    target = root.joinpath(*parts.parts)
    cursor = root
    for part in (None, *parts.parts):
        if part is not None:
            cursor /= part
        if cursor.exists() or cursor.is_symlink():
            info = cursor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Linked source path is not allowed')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Source escaped library root')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2] / 'hardware_library')
    parser.add_argument('--fetch-missing', action='store_true', help='Download missing sources only; changed files remain errors')
    parser.add_argument('--proxy', help='Optional HTTPS proxy URL, for example http://127.0.0.1:7898')
    args = parser.parse_args()
    root = args.root.absolute()
    lock = json.loads((root / 'sources.lock.json').read_text(encoding='utf-8'))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'https': args.proxy}) if args.proxy else urllib.request.ProxyHandler())
    failures = []
    for entry in lock['files']:
        path = target_path(root, entry['local_path'])
        if not path.exists() and args.fetch_missing:
            url = entry.get('url')
            if not isinstance(url, str) or not url.startswith('https://'):
                failures.append({'ref': entry['local_path'], 'error': 'missing_https_source'})
                continue
            try:
                with opener.open(urllib.request.Request(url, headers={'User-Agent': 'Hardware-CLAW-source-maintenance'}), timeout=60) as r:
                    blob = r.read(entry['bytes'] + 1)
                if len(blob) != entry['bytes'] or hashlib.sha256(blob).hexdigest() != entry['sha256']:
                    raise ValueError('Downloaded source differs from lock')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
            except Exception as exc:
                failures.append({'ref': entry['local_path'], 'error': type(exc).__name__})
                continue
        if not path.is_file():
            failures.append({'ref': entry['local_path'], 'error': 'missing'})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            failures.append({'ref': entry['local_path'], 'error': 'hash_mismatch'})
    print(json.dumps({'files': len(lock['files']), 'failures': failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
