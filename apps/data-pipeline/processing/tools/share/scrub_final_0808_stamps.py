"""Remove/replace all 20260808 stamps inside repo-root 최종본_20260809/."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
ROOT = REPO / "최종본_20260809"
SHARE = REPO / "docs" / "팀공유"
ANALYSIS = REPO / "docs" / "data" / "analysis"
KST = ZoneInfo("Asia/Seoul")


def _rm(p: Path) -> None:
    if not p.exists():
        return
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()


def _cp_tree(src: Path, dest: Path) -> bool:
    if not src.exists():
        return False
    _rm(dest)
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    else:
        shutil.copytree(src, dest)
    return True


def _rename_path(p: Path, new_name: str) -> Path:
    dest = p.parent / new_name
    if dest.exists() and dest != p:
        _rm(dest)
    p.rename(dest)
    return dest


def _copy_md_as(src_name: str, dest_dir: Path, new_name: str) -> None:
    src = SHARE / src_name
    if not src.is_file():
        # already inside pack
        old = dest_dir / src_name
        if old.is_file():
            text = old.read_text(encoding="utf-8")
            dest = dest_dir / new_name
            dest.write_text(text, encoding="utf-8")
            if old != dest:
                old.unlink()
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / new_name)
    old = dest_dir / src_name
    if old.is_file() and old.name != new_name:
        old.unlink()


def main() -> None:
    assert ROOT.is_dir(), ROOT
    actions: list[str] = []

    # 1) kill nested 0808 mega-duplicate
    for name in ("최종본_통합_0808분류", "최종본_통합_20260808"):
        p = ROOT / "03_시각자료" / name
        if p.exists():
            _rm(p)
            actions.append(f"rm {p.relative_to(ROOT)}")

    # 2) replace viz series with 0809 from team-share
    viz_pairs = [
        ("D1_최신화의미_20260808", "D1_최신화의미_20260809"),
        ("도시혼잡_시계열_20260808", "도시혼잡_시계열_20260809"),
        ("돌발_UTIC_분석_20260808", "돌발_UTIC_분석_20260809"),
        ("상태수집_패널차트_20260808", "상태수집_패널차트_20260809"),
        ("시각화팩_통합_20260808", "시각화팩_통합_20260809"),
        ("시간대_가용률_20260808", "시간대_가용률_20260809"),
    ]
    viz_root = ROOT / "03_시각자료"
    viz_root.mkdir(exist_ok=True)
    for old, new in viz_pairs:
        _rm(viz_root / old)
        if _cp_tree(SHARE / new, viz_root / new):
            actions.append(f"viz {new}")
        else:
            actions.append(f"MISSING {new}")

    # 3) AI briefing: drop old, copy fresh pack if we rebuild; else strip and use 0809 viz only
    ai_old = viz_root / "시각자료_AI해설팩"
    ai_old2 = viz_root / "시각자료_AI해설팩_20260808"
    _rm(ai_old)
    _rm(ai_old2)
    # keep only 0809 viz pack as main; optional slim AI folder from pack script later
    actions.append("rm AI해설팩_0808")

    # 4) EDA: only 0809
    eda02 = ROOT / "02_EDA_KPI"
    _rm(eda02 / "EDA_최종_20260808")
    _rm(eda02 / "EDA_KPI_보고서_20260808.md")
    if _cp_tree(SHARE / "EDA_최종_20260809", eda02 / "EDA_최종_20260809"):
        actions.append("EDA_최종_20260809")
    # regenerate EDA_KPI md as 0809 name (copy + rename)
    kpi_src = SHARE / "EDA_KPI_보고서_20260808.md"
    if kpi_src.is_file():
        text = kpi_src.read_text(encoding="utf-8")
        text = text.replace("20260808", "20260809").replace("2026-08-08", "2026-08-09")
        (eda02 / "EDA_KPI_보고서_20260809.md").write_text(text, encoding="utf-8")
        actions.append("EDA_KPI_보고서_20260809.md")

    # 5) 00 docs: rename stamps 0808 -> 0809
    d00 = ROOT / "00_먼저읽기"
    renames_md = [
        ("이름_쉬운말_안내_20260808.md", "이름_쉬운말_안내_20260809.md"),
        ("최종파일명_확정_20260808.md", "최종파일명_확정_20260809.md"),
        ("ETA_동대구고정_한계_조장필독_20260808.md", "ETA_동대구고정_한계_조장필독_20260809.md"),
        ("모델적합도_과적합_완료패키지_20260808.md", "모델적합도_과적합_완료패키지_20260809.md"),
        ("D1_KPI_핸드오프_20260808.md", "D1_KPI_핸드오프_20260809.md"),
        ("EDA_KPI_보고서_20260808.md", "EDA_KPI_보고서_20260809.md"),
    ]
    for old, new in renames_md:
        src = d00 / old
        if src.is_file():
            text = src.read_text(encoding="utf-8")
            # keep factual historical dates inside body if needed; filename must be 0809
            (d00 / new).write_text(text, encoding="utf-8")
            src.unlink()
            actions.append(f"00 {new}")
        elif (SHARE / old).is_file():
            shutil.copy2(SHARE / old, d00 / new)
            actions.append(f"00 copy {new}")

    # 6) HGB: rename *_20260808 -> *_20260809 (content is final selection; stamp = delivery day)
    hgb = ROOT / "04_HGB_피처_과적합"
    if hgb.is_dir():
        for p in list(hgb.iterdir()):
            if "20260808" in p.name:
                new = p.name.replace("20260808", "20260809")
                _rename_path(p, new)
                actions.append(f"hgb {new}")

    # 7) model data folders
    m05 = ROOT / "05_모델데이터"
    for old, new in [
        ("ETA_실제_라벨_20260808", "ETA_실제_라벨_20260809"),
        ("arrival_availability_replay_20260808", "arrival_availability_replay_20260809"),
    ]:
        p = m05 / old
        if p.exists():
            _rename_path(p, new)
            actions.append(f"05 {new}")

    # 8) nuke any remaining path component with 20260808 under ROOT (except inside file contents)
    left = []
    for p in sorted(ROOT.rglob("*"), key=lambda x: len(str(x)), reverse=True):
        if "20260808" in p.name or "0808" in p.name:
            # rename if sibling 0809 not needed
            if p.name.replace("20260808", "20260809") != p.name:
                target = p.parent / p.name.replace("20260808", "20260809")
                if target.exists():
                    _rm(p)
                    actions.append(f"rm dup {p.relative_to(ROOT)}")
                else:
                    _rename_path(p, target.name)
                    actions.append(f"rename {target.relative_to(ROOT)}")
            elif "0808" in p.name:
                _rm(p)
                actions.append(f"rm {p.relative_to(ROOT)}")

    # verify
    for p in ROOT.rglob("*"):
        if re.search(r"20260808|0808", p.name):
            left.append(str(p.relative_to(ROOT)).replace("\\", "/"))

    # 9) leftover wrong path under docs/팀공유
    stray = SHARE / "최종본_20260809"
    if stray.is_dir():
        _rm(stray)
        actions.append("rm docs/팀공유/최종본_20260809 stray")

    # README
    (ROOT / "README.md").write_text(
        f"""# 최종본_20260809 — DA① 로컬 정본

| | |
|---|---|
| **위치** | repo 최상위 `최종본_20260809/` |
| **생성** | {datetime.now(KST).isoformat(timespec="seconds")} |
| **현재표 as_of** | 2026-08-09T07:23:21+09:00 |
| **오늘 pull** | `from_lightsail_20260809_072742` |
| **점수** | 없음 → ② |

**파일명 stamp는 전부 20260809.** (0808 폴더/파일명 제거)

## 폴더

| 폴더 | 내용 |
|---|---|
| `00_먼저읽기/` | 계약·필독 md (0809 파일명) |
| `01_계약_한계/` | 주차·usage·갭·파생 |
| `02_EDA_KPI/` | EDA_최종_20260809 · KPI |
| `03_시각자료/` | 가용률·패널·혼잡·UTIC·시각화팩 **20260809** |
| `04_HGB_피처_과적합/` | 피처·과적합 (**파일명 20260809**) |
| `05_모델데이터/` | 현재표·시간표·라벨 |
| `06_수집_pull/` | Lightsail pull |
| `07_검사_게이트_최신_20260809/` | IQR·타당성·연동·게이트 |
| `08_IQR_이상치검사_최신/` | IQR |

```
DA① | FINAL 20260809 | no 0808 stamps
```
""",
        encoding="utf-8",
    )
    (ROOT / "00_먼저읽기" / "README.md").write_text(
        (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8"
    )

    meta = {
        "scrubbed_at": datetime.now(KST).isoformat(timespec="seconds"),
        "actions_n": len(actions),
        "left_0808_names": left,
        "actions_tail": actions[-40:],
    }
    (ROOT / "pack_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "left": left, "actions_n": len(actions)}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
