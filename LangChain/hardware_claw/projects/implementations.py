"""Explicit implementation choices, bound to registered knowledge, never device names."""
import hashlib
import re

from .service import fail


def choice(design, instance):
    return design.get("implementations", {}).get(instance, {"mode": "catalog", "api_refs": []})


def pin_choices(design, hardware, catalog):
    """Record only user/agent declarations and source identity, not feasibility verdicts."""
    choices = design.get("implementations", {})
    if set(choices) - set(hardware):
        fail("INVALID_IMPLEMENTATION", "实现方案只能引用当前设计中的元件实例（板卡为mcu）。")
    evidence = {}
    board_refs = set(hardware["mcu"]["profile"].get("driver_profile", {}).get("framework_api_refs", []))
    for instance, info in hardware.items():
        selected = choice(design, instance)
        if selected["mode"] != "framework":
            continue
        allowed = board_refs | set(info["profile"].get("driver_profile", {}).get("framework_api_refs", []))
        refs = selected["api_refs"]
        if not refs or set(refs) - allowed:
            fail("INVALID_IMPLEMENTATION", "framework方案须引用已登记的framework_api_refs；不能用例程、任意路径或资料缺失代替API依据。")
        evidence[instance] = [{"ref": ref, "sha256": hashlib.sha256(catalog._bytes(
            ref, prefixes=("upstream/", "supplements/sources/"))).hexdigest()} for ref in sorted(set(refs))]
    return evidence


def dependency_problems(state):
    """Keep pinned sources; a framework choice removes that device's mandatory library."""
    design, hardware = state["design"], state.get("hardware", {})
    known, required = set(), set()
    for instance, info in hardware.items():
        deps = {(d["name"], d["version"]) for d in info["profile"].get("driver_profile", {}).get("dependencies", [])}
        known |= deps
        if choice(design, instance)["mode"] == "catalog":
            required |= deps
    actual = [(d["name"], d["version"]) for d in design["dependencies"]]
    problems = []
    if len(set(actual)) != len(actual) or len({name for name, _ in actual}) != len(actual):
        problems.append(("DUPLICATE_DEPENDENCY", "重复依赖或同一包的冲突版本。"))
    for name, version in actual:
        # Prevent paths, URLs, interpolation and version ranges from reaching PIO.
        safe = (re.fullmatch(r"(?:[A-Za-z0-9_-]+/)?[A-Za-z0-9][A-Za-z0-9_. +\-]*", name)
                and ".." not in name and re.fullmatch(r"[0-9][0-9A-Za-z.+\-]*", version))
        if not safe or (name, version) not in known:
            problems.append(("UNSUPPORTED_DEPENDENCY", f"依赖{name}@{version}不在当前硬件的已登记固定依赖中；需先维护可信包来源。"))
    for name, version in sorted(required - set(actual)):
        problems.append(("MISSING_DESIGN_DEPENDENCY", f"所选catalog实现需要{name}@{version}；替代实现须显式选择framework并登记API依据。"))
    return problems
