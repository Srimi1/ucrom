"""Turn results.json into docs/test-report/REPORT.md."""

from pathlib import Path

ICON = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}


def _section(nodeid: str) -> str:
    f = nodeid.split("::")[0].split("/")[-1]
    return {
        "test_00_image_static.py": "1. The built OS image",
        "test_10_boot.py": "2. Boot on the emulated phone",
        "test_20_touch_only.py": "3. Touch-only enforcement (keyboards and mice blocked)",
        "test_30_touch_ux.py": "4. Using the phone by touch only",
        "test_40_apps.py": "5. AI agents and developer apps",
        "test_50_daemons.py": "6. ucrom hardware helpers (simulated hardware)",
        "test_60_hotdog.py": "7. OnePlus 7T Pro McLaren (hotdog) build",
        "test_61_device_artifacts.py": "8. Flashable images",
        "test_62_bridges.py": "9. Hardware bridge packages (Halium)",
        "test_63_soc_matrix.py": "10. Snapdragon chip / phone matrix",
    }.get(f, f)


def write_markdown(data: dict, out: Path) -> None:
    tests = data["tests"]
    counts = {}
    for t in tests.values():
        counts[t["outcome"]] = counts.get(t["outcome"], 0) + 1
    lines = [
        "# ucrom test report",
        "",
        f"Generated {data['generated']} by `make report` (pytest). "
        "Everything below was produced by the automated suite in `tests/` "
        "against the images built from this repository.",
        "",
        f"**{counts.get('passed', 0)} passed, {counts.get('failed', 0)} failed, "
        f"{counts.get('skipped', 0)} skipped** out of {len(tests)} tests.",
        "",
    ]
    sections: dict[str, list] = {}
    for nodeid, t in tests.items():
        sections.setdefault(_section(nodeid), []).append((nodeid, t))
    for name in sorted(sections, key=lambda s: (int(s.split(".")[0]) if s[0].isdigit() else 99, s)):
        lines += [f"## {name}", "", "| Result | Test | Time |", "|---|---|---|"]
        for nodeid, t in sections[name]:
            lines.append(f"| {ICON.get(t['outcome'], t['outcome'])} | {t.get('title', nodeid)} | {t.get('duration', '')} s |")
        lines.append("")
        for nodeid, t in sections[name]:
            if not (t.get("notes") or t.get("shots") or t.get("error")):
                continue
            lines.append(f"### {t.get('title', nodeid)}")
            lines.append("")
            for n in t.get("notes", []):
                lines.append(f"- {n}")
            if t.get("error"):
                lines += ["", "```", t["error"].strip()[-1500:], "```"]
            if t.get("shots"):
                lines.append("")
                lines.append(" ".join(
                    f'<img src="{s["file"]}" width="180" alt="{s["label"]}" title="{s["label"]}">'
                    for s in t["shots"]))
            lines.append("")
    lines += ["## Versions and image checksums", "", "```"]
    for k, v in data["versions"].items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines += [f"  {x}" for x in v]
        else:
            lines.append(f"{k}: {v}")
    lines += ["```", ""]
    out.write_text("\n".join(lines))
