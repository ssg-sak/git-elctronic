"""One-shot: move pack/scrape scripts analysis/ -> tools/share/."""
from __future__ import annotations

import shutil
from pathlib import Path

PROC = Path(__file__).resolve().parents[1]
SRC = PROC / "analysis"
DST = PROC / "tools" / "share"

FILES = [
    "pack_coverage_gap_unified.py",
    "pack_info_new_stations_team.py",
    "pull_new_apt_charger_pack.py",
    "scrape_duryu_seohan_forest.py",
    "compare_new_apt_vs_info.py",
    "probe_info_coverage_gaps.py",
]


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        a, b = SRC / name, DST / name
        if a.exists() and not b.exists():
            shutil.move(str(a), str(b))
            print("moved", name)
        elif b.exists():
            print("already", name)
            if a.exists() and a.resolve() != b.resolve():
                # leave stub only
                pass
        else:
            print("missing", name)
            continue

        # fix REPO depth: was parents[4] from analysis/, now parents[5] from tools/share/
        text = b.read_text(encoding="utf-8")
        old = 'Path(__file__).resolve().parents[4]'
        new = 'Path(__file__).resolve().parents[5]'
        if old in text:
            b.write_text(text.replace(old, new), encoding="utf-8")
            print("  fixed REPO parents", name)

        stub = SRC / name
        stub.write_text(
            (
                f'"""Deprecated path — use processing/tools/share/{name}\n\n'
                f"Run:\n  python apps/data-pipeline/processing/tools/share/{name}\n"
                '"""\n'
                "from __future__ import annotations\n\n"
                "import runpy\n"
                "from pathlib import Path\n\n"
                f'_TARGET = Path(__file__).resolve().parents[1] / "tools" / "share" / "{name}"\n\n'
                'if __name__ == "__main__":\n'
                '    runpy.run_path(str(_TARGET), run_name="__main__")\n'
            ),
            encoding="utf-8",
        )
        print("  stub", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
