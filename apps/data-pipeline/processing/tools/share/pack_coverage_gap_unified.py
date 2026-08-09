"""One desktop zip: all coverage-gap share materials."""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
DESK = Path.home() / "Desktop"
KST = ZoneInfo("Asia/Seoul")


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    pack = f"EV_SafeCharge_커버리지갭_통합공유_{stamp}"
    root = DESK / pack
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    pairs = [
        (
            REPO / "docs/팀공유/커버리지갭_단계계획_20260731.md",
            "00_단계계획/커버리지갭_단계계획_20260731.md",
        ),
        (REPO / "docs/팀공유/인포커버리지갭_20260731", "01_커버리지갭_점검"),
        (REPO / "docs/팀공유/인포신규충전소_20260731", "02_인포신규충전소"),
        (REPO / "docs/팀공유/두류역서한포레스트_20260731", "03_두류역서한포레스트"),
        (REPO / "docs/팀공유/신축단지_인포대조_20260731", "04_신축단지_인포대조_1차"),
        (REPO / "docs/팀공유/신축단지_충전데이터팩_20260731", "05_신축단지_충전데이터팩"),
        (
            REPO / "docs/팀공유/D2_lag정합_쉬운설명_20260731.md",
            "06_참고_D2_lag/D2_lag정합_쉬운설명_20260731.md",
        ),
    ]

    copied: list[str] = []
    for src, dest in pairs:
        src = Path(src)
        dst = root / dest
        if not src.exists():
            print("MISSING", src)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            copied.append(dest + "/")
        else:
            shutil.copy2(src, dst)
            copied.append(dest)

    readme = "\n".join(
        [
            "# EV SafeCharge — 커버리지 갭 통합 공유 팩",
            "",
            "팀톡/공유용 **단일 압축**입니다. 폴더만 순서대로 보면 됩니다.",
            "",
            "## 읽는 순서",
            "1. `00_단계계획` — 앞으로 뭘 할지",
            "2. `01_커버리지갭_점검` — 구멍 종류(Type A/B/C) 쉬운 설명",
            "3. `02_인포신규충전소` — info 덤프에 새로 생긴 statId (신설 확정 아님)",
            "4. `03_두류역서한포레스트` — Type A 대표 사례",
            "5. `04_신축단지_인포대조_1차` — 이름 매칭 1차",
            "6. `05_신축단지_충전데이터팩` — **2025+2026 31단지** 충전 데이터 (메인)",
            "7. `06_참고_D2_lag` — 별건(lag 정합) 참고",
            "",
            "## 한 줄 결론",
            "- 2025/2026 신축 단지명으로 EvCharger info에 잡히는 경우 ≈ 거의 없음",
            "- MVP는 관측 가능 충전소 기준. 완전 목록 주장 금지",
            "- 신설 확정 ≠ info에 ID가 생김",
            "",
            f"생성일: {datetime.now(KST).isoformat()}",
            "",
        ]
    )
    (root / "README_먼저읽기.md").write_text(readme, encoding="utf-8")

    zpath = DESK / f"{pack}.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in root.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=f"{pack}/{f.relative_to(root).as_posix()}")

    print("FOLDER", root)
    print("ZIP", zpath)
    print("MB", round(zpath.stat().st_size / 1e6, 2))
    for c in copied:
        print(" -", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
