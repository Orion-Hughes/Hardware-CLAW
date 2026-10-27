"""Exercise the exact tool interfaces locally, without creating an LLM."""
import argparse
import json

from ..tools.hardware_catalog import get_hardware_info, search_hardware


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="搜索硬件；默认仅本地配置")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--kind", default="")
    search.add_argument("--scope", choices=["local", "upstream", "all"], default="local")
    search.add_argument("--status", choices=["any", "documented_not_tested", "blocked", "unreviewed", "metadata_only"], default="any")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--offset", type=int, default=0)
    get = commands.add_parser("get", help="读取指定ID的详细信息")
    get.add_argument("hardware_id")
    get.add_argument("--shared", action="store_true")
    get.add_argument("--examples", action="store_true")
    args = parser.parse_args()
    if args.command == "search":
        result = search_hardware.invoke({"query": args.query, "kind": args.kind, "scope": args.scope,
                                        "generation_status": args.status, "limit": args.limit, "offset": args.offset})
    else:
        result = get_hardware_info.invoke({"hardware_id": args.hardware_id, "include_shared": args.shared, "include_examples": args.examples})
    if isinstance(result, str):
        result = json.loads(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["execution_status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
