"""Build a narrowly patched, pinned upstream MCP backend. No firmware patches.

Usage: project Python build_backend.py [--source <prepared upstream>] [--skip-install]
Downloads/builds stay under temp; installed bundle stays under ignored tools/.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[3]
REVISION = "940b7237d26f"
PATCH_VERSION = "0.29.0-hwclaw.1"
ARCHIVE_SHA256 = "eccd0b48fcbc0a6342048d4b3491a7489a9da3004223649f04ce0b55cfa12669"
FILES = {
    "WokwiMCPTools.ts": "dd930695692acf16b9eb8c7f3531db0019295898506e4bdb8f4520508ed6147a",
    "SimulationManager.ts": "a797012d119ba990f06a920addba50709634343b93cc7467c9a6e79758a59586",
    "MCPServer.ts": "d88307f4c7c89476957a9eed9f8413ada76c82d449601dba7676edbe07fee86f",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_source(source):
    folder = source / "packages/cli/src/mcp"
    texts = {}
    for name, digest in FILES.items():
        if sha(folder / name) != digest:
            raise ValueError(f"Upstream source mismatch: {name}. Refuse an unreviewed patch.")
        texts[name] = (folder / name).read_text(encoding="utf-8")

    def replace(name, old, new):
        if texts[name].count(old) != 1:
            raise ValueError(f"Patch context mismatch: {name}")
        texts[name] = texts[name].replace(old, new, 1)

    replace("WokwiMCPTools.ts", "import type { Tool }", "import type { CallToolResult, Tool }")
    replace("WokwiMCPTools.ts", "Promise<{ content: Array<{ type: 'text'; text: string }> }>", "Promise<CallToolResult>")
    replace("WokwiMCPTools.ts", "description: 'Read the value of a pin'", "description: 'Read digital logic level only. Cannot measure voltage, ADC values or PWM duty cycle.'")
    replace("WokwiMCPTools.ts", "type: 'text',\n                text: `Screenshot taken (base64): ${screenshot.substring(0, 100)}...`,",
            "type: 'image',\n                mimeType: 'image/png',\n                data: screenshot,")
    replace("WokwiMCPTools.ts", "text: `Pin ${args.pin} on ${args.partId}: ${pinValue.value} (${pinValue.voltage}V)`,",
            "text: `Pin ${args.pin} on ${args.partId}: ${pinValue.value}. Digital logic only; voltage is not available.`,")
    replace("WokwiMCPTools.ts", "const pinValue = await this.simulationManager.readPin(args.partId, args.pin);\n          return {",
            "const pinValue = await this.simulationManager.readPin(args.partId, args.pin);\n          return {\n            structuredContent: {\n              partId: args.partId, pin: args.pin, value: pinValue.value,\n              voltage: null, scope: 'digital_logic_only', rawResponse: pinValue,\n              limitation: 'Cannot measure voltage, ADC values or PWM duty cycle.',\n            },")
    replace("SimulationManager.ts", "return {\n      value: result.value,\n      voltage: result.voltage,\n    };", "return result; // Preserve upstream fields verbatim for diagnostics; never infer voltage.")
    replace("MCPServer.ts", "name: 'wokwi-cli',\n        version,", f"name: 'wokwi-cli-hwclaw',\n        version: '{PATCH_VERSION}',")
    # Preserve upstream API handshake version. Only MCP's advertised backend identifies the patch.
    for name, text in texts.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()
    work = ROOT / "temp/wokwi-mcp-build" / uuid.uuid4().hex
    work.mkdir(parents=True)
    source = args.source.resolve() if args.source else None
    if source is None:
        archive = work / "upstream.tar.gz"
        urllib.request.urlretrieve(f"https://codeload.github.com/wokwi/wokwi-cli/tar.gz/{REVISION}", archive)
        if sha(archive) != ARCHIVE_SHA256:
            raise ValueError("Upstream archive checksum mismatch")
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter="data")
        source = work / f"wokwi-cli-{REVISION}"
    if not source.is_relative_to((ROOT / "temp").resolve()):
        raise ValueError("Build source must be below project temp")
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise RuntimeError("Node.js and npm are required")
    env = dict(os.environ, npm_config_cache=str(ROOT / "temp/npm-cache"))
    if not args.skip_install:
        subprocess.run([npm, "exec", "--yes", "--package=pnpm@10.17.1", "--", "pnpm", "install", "--frozen-lockfile", "--ignore-scripts", "--store-dir", str(ROOT / "temp/pnpm-store")], cwd=source, env=env, check=True, timeout=600)
    patch_source(source)
    subprocess.run([node, "packages/diagram-lint/scripts/build-parts.mjs"], cwd=source, check=True, timeout=60)
    bundle = source / "hwclaw-cli.cjs"
    build_script = source / "hwclaw-bundle.mjs"
    build_script.write_text("""import {build} from 'esbuild';
import path from 'node:path';
await build({platform:'node', entryPoints:['packages/cli/src/main.ts'], outfile:'hwclaw-cli.cjs', bundle:true,
  alias:{'@wokwi/client':path.resolve('packages/client/src/index.ts'),
         '@wokwi/diagram-lint':path.resolve('packages/diagram-lint/src/index.ts'),
         '@wokwi/rfc2217':path.resolve('packages/rfc2217/src/index.ts')},
  define:{'process.env.WOKWI_CONST_CLI_VERSION':JSON.stringify('0.29.0'),
          'process.env.WOKWI_CONST_CLI_SHA':JSON.stringify('940b7237d26f')}});
""", encoding="utf-8")
    subprocess.run([node, str(build_script)], cwd=source, check=True, timeout=120)
    target = ROOT / "tools/wokwi-mcp" / PATCH_VERSION
    target.mkdir(parents=True, exist_ok=True)
    checksum = sha(bundle)
    installed = target / "cli.cjs"
    if installed.exists() and sha(installed) != checksum:
        raise ValueError("Installed patch differs; bump patch version instead of overwriting")
    shutil.copy2(bundle, installed)
    shutil.copy2(source / "LICENSE", target / "UPSTREAM_LICENSE")
    manifest = {"patch_version": PATCH_VERSION, "upstream_revision": REVISION,
                "upstream_archive_sha256": ARCHIVE_SHA256, "bundle_sha256": checksum,
                "source_sha256": FILES, "patched_source_sha256": {n:sha(source/'packages/cli/src/mcp'/n) for n in FILES},
                "patch_script_sha256": sha(Path(__file__)), "node_version": subprocess.check_output([node, '--version'],text=True).strip()}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"installed": str(installed), **manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
