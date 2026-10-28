"""Select a locally verified upstream patch, otherwise retain the official binary."""
import hashlib
import json
import shutil
from ..projects.service import ROOT, fail
from .simulator import CLI

PATCH_VERSION = "0.29.0-hwclaw.1"
PATCH_FOLDER = ROOT / "tools/wokwi-mcp" / PATCH_VERSION


def select_backend():
    manifest_path = PATCH_FOLDER / "manifest.json"
    if not manifest_path.exists():
        return {"command": str(CLI), "prefix": [], "version": "0.29.0", "kind": "official_binary"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = PATCH_FOLDER / "cli.cjs"
    if (manifest.get("patch_version") != PATCH_VERSION or manifest.get("upstream_revision") != "940b7237d26f"
            or not bundle.is_file() or hashlib.sha256(bundle.read_bytes()).hexdigest() != manifest.get("bundle_sha256")):
        fail("MCP_BACKEND_CHANGED", "本地MCP修复版缺失或哈希变化，请重新构建核对；不静默回退。")
    node = shutil.which("node")
    if not node:
        fail("MCP_NODE_UNAVAILABLE", "运行本地MCP修复版需要Node.js。")
    return {"command": node, "prefix": [str(bundle)], "version": PATCH_VERSION,
            "kind": "upstream_with_local_generic_patch", "bundle_sha256": manifest["bundle_sha256"]}
