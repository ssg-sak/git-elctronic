"""Archive older dated team-share packs; keep latest of each series at root.

Does NOT delete — only moves into docs/팀공유/_archive/.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
SHARE = REPO / "docs" / "팀공유"
ARCHIVE = SHARE / "_archive"
KST = ZoneInfo("Asia/Seoul")
STAMP_RE = re.compile(r"(20\d{6})")

# Recurring series: keep max YYYYMMDD at root, archive older.
SERIES_PREFIXES = [
    "D1_최신화의미_",
    "도시혼잡_시계열_",
    "돌발_UTIC_분석_",
    "시간대_가용률_",
    "시각화팩_통합_",
    "상태수집_패널차트_",
    "신축단지_인포대조_",
    "주차_혼잡_EDA_",
    "인포커버리지갭_",
    "D1_KPI_핸드오프_",
    "팀공유_핸드오프_①to②_",
    "위경도_피처유의성_",
    "피처적합도_비교_",
    "ETA_실제_라벨_",
    "ETA_보정샘플_",
    "피처적합도_HGB_도착ETA_",
    "피처선정_최종_HGB_도착ETA_",
    "과적합위험_HGB_도착ETA_",
    "IQR_이상치검사_",
]

# Always keep at root (exact names). Series "latest" is kept separately.
KEEP_EXACT = {
    "README.md",
    "_archive",
    # 계약·한계 (상시)
    "커버리지갭_단계계획_20260731.md",
    "주차_realtime_428_한계_20260803.md",
    "충전이력_usage_희소성_과적합_20260804.md",
    "시각자료_해석설명서_20260731.md",
    "시간대_가용률_평균중앙값_해설_20260731.md",
    "결측률_팀원쉬운보고_20260731.md",
    "EDA_팀원쉬운보고_20260731.md",
    "주차장요금_추출_20260803",
    "주차점수_검증_20260803",
    "요금_BE전달_20260731",
    "요금_팀공유쉬운보고_20260731",
    # 8/8~8/9 전달 정본
    "이름_쉬운말_안내_20260808.md",
    "최종파일명_확정_20260808.md",
    "ETA_동대구고정_한계_조장필독_20260808.md",
    "모델적합도_과적합_완료패키지_20260808.md",
    "최종패키지_조장전달_목록_20260809.md",
    "최종패키지_명령_초안_20260806.md",
    "핵심갭_개선계획_20260806.md",
    "파생변수_검토_도착라벨_20260806.md",
    "파생변수_derived_v0_20260806",
    "IQR_이상치_모델해석_20260806.md",
    "DA2_질문확인_20260807.md",
    "누적확인_14일_20260807.md",
    "차트유형_갤러리_20260806",
    "최종본_통합_20260808",
    "EDA_최종_20260808",
    "EDA_KPI_보고서_20260808.md",
    "시각자료_AI해설팩_20260808",
    "최종본_조장전달_지금기준_20260809",
    "최종본_20260809",
}

# Move leftover dated / misc clutter (exact names or prefixes).
FORCE_ARCHIVE_PREFIXES = (
    "팀공유_TMAP_",
    "팀공유_UTIC_",
    "팀공유_useTime",
    "팀공유_충전속도",
    "팀공유_ETA_",
    "팀공유_202607",
    "EV_SafeCharge_",
    "가용률_혼잡_교차표_",
    "공용소_모델후보_",
    "이용이력_대구_",
    "충전소_수동테스트_",
    "운영규칙_팀원쉬운보고_",
    "주차게이트_판정_",
    "데이터타당성_",
    "요금_단가_",
    "KPI_EDA_",
    "신축단지_충전데이터팩_",
    "레퍼런스_모델성능_",
)


def _stamp(name: str) -> str | None:
    m = STAMP_RE.search(name)
    return m.group(1) if m else None


def _dest_for(name: str) -> Path:
    st = _stamp(name)
    if st:
        return ARCHIVE / st[:6] / name
    return ARCHIVE / "misc" / name


def main() -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    moved: list[dict] = []
    kept_latest: dict[str, str] = {}

    # 1) series: keep newest stamp
    by_series: dict[str, list[Path]] = defaultdict(list)
    for p in SHARE.iterdir():
        if p.name in KEEP_EXACT or p.name == "_archive":
            continue
        for pref in SERIES_PREFIXES:
            if p.name.startswith(pref) and _stamp(p.name):
                by_series[pref].append(p)
                break

    for pref, paths in by_series.items():
        paths = sorted(paths, key=lambda x: _stamp(x.name) or "")
        latest = paths[-1]
        kept_latest[pref] = latest.name
        for p in paths[:-1]:
            dest = _dest_for(p.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
            shutil.move(str(p), str(dest))
            moved.append({"from": p.name, "to": str(dest.relative_to(SHARE)).replace("\\", "/")})

    # 2) force-archive misc leftovers still at root
    for p in list(SHARE.iterdir()):
        if p.name in KEEP_EXACT or p.name == "_archive":
            continue
        if any(p.name.startswith(pref) for pref in SERIES_PREFIXES):
            continue  # latest of series stays
        if any(p.name.startswith(pref) for pref in FORCE_ARCHIVE_PREFIXES) or p.suffix == ".zip":
            dest = _dest_for(p.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
            shutil.move(str(p), str(dest))
            moved.append({"from": p.name, "to": str(dest.relative_to(SHARE)).replace("\\", "/")})

    # 3) archive README
    (ARCHIVE / "README.md").write_text(
        "\n".join(
            [
                "# 팀공유 아카이브",
                "",
                "루트(`docs/팀공유/`)에는 **최종본(최신 stamp) + 계약/설명**만 둡니다.",
                "과거 날짜 팩·핸드오프는 여기로 이동합니다. **삭제하지 않음.**",
                "",
                f"- 정리 시각: {datetime.now(KST).isoformat(timespec='seconds')}",
                f"- 이번 이동: {len(moved)}건",
                "",
                "## 규칙",
                "",
                "1. 반복 시리즈 → 최신 stamp만 루트",
                "2. 전날은 `_archive/YYYYMM/`",
                "3. 팀에 링크 줄 때 루트·`README.md`만 기준",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # 4) slim root README (plain names)
    def _k(pref: str, default: str) -> str:
        return kept_latest.get(pref, default)

    today = datetime.now(KST).strftime("%Y-%m-%d")
    handoff = _k("팀공유_핸드오프_①to②_", "팀공유_핸드오프_①to②_20260804.md")
    kpi = _k("D1_KPI_핸드오프_", "D1_KPI_핸드오프_20260808.md")
    viz = _k("시각화팩_통합_", "시각화팩_통합_20260808")
    avail = _k("시간대_가용률_", "시간대_가용률_20260808")
    d1 = _k("D1_최신화의미_", "D1_최신화의미_20260808")
    cong = _k("도시혼잡_시계열_", "도시혼잡_시계열_20260808")
    utic = _k("돌발_UTIC_분석_", "돌발_UTIC_분석_20260808")
    panel = _k("상태수집_패널차트_", "상태수집_패널차트_20260808")
    eta = _k("ETA_실제_라벨_", "ETA_실제_라벨_20260808")
    feat = _k("피처선정_최종_HGB_도착ETA_", "피처선정_최종_HGB_도착ETA_20260808")
    fit = _k("피처적합도_HGB_도착ETA_", "피처적합도_HGB_도착ETA_20260808")
    over = _k("과적합위험_HGB_도착ETA_", "과적합위험_HGB_도착ETA_20260808")

    readme = f"""# 팀공유 모음 (DA①)

> **여기만 보면 됨.** 최종본만 루트. 과거 → [`_archive/`](./_archive/) (삭제 없음)

| | |
|---|---|
| **담당** | AI·데이터 ① |
| **말하는 이름** | **현재표** / **시간표** ([안내](./이름_쉬운말_안내_20260808.md)) |
| **점수/추천** | 이 폴더에 **없음** → ② |

---

## 최종 패키지 ({today})

| 폴더/파일 | 한 줄 | 누구에게 |
|---|---|---|
| **[`최종패키지_조장전달_목록_20260809.md`](./최종패키지_조장전달_목록_20260809.md)** | 8/9 zip·체크리스트 | **조장** |
| **[`{handoff}`](./{handoff})** | ①→② 계약 핸드오프 | **②** |
| **[`{kpi}`](./{kpi})** | 현재표·KPI 숫자 | 전원 · **②** |
| **[`모델적합도_과적합_완료패키지_20260808.md`](./모델적합도_과적합_완료패키지_20260808.md)** | HGB 적합·과적합 한 장 | **②·조장** |
| **[`{feat}/`](./{feat}/)** | 최종 피처 9개 BI | **②** |
| **[`{fit}/`](./{fit}/)** | 도착·ETA 적합도 | **②** |
| **[`{over}/`](./{over}/)** | 과적합 위험 | **②** |
| **[`{eta}/`](./{eta}/)** | 도착 라벨·TMAP ETA | **②** |
| **[`ETA_동대구고정_한계_조장필독_20260808.md`](./ETA_동대구고정_한계_조장필독_20260808.md)** | 동대구 고정 ETA 한계 | **조장** |
| **[`{viz}/`](./{viz}/)** | 통합 시각화 팩 | 전원 · **조장** |
| **[`{panel}/`](./{panel}/)** | 상태수집 패널 차트 | 전원 · ② |
| **[`{avail}/`](./{avail}/)** | 시간대 가용률 | 전원 · ② |
| **[`{d1}/`](./{d1}/)** | 현재표 숫자 의미 | 전원 · ② |
| **[`{cong}/`](./{cong}/)** | 도시 혼잡 | 전원 · BE·② |
| **[`{utic}/`](./{utic}/)** | UTIC 돌발 | 전원 |

---

## 계약·가이드 (상시)

| 파일 | 한 줄 |
|---|---|
| [`이름_쉬운말_안내_20260808.md`](./이름_쉬운말_안내_20260808.md) | 현재표/시간표 말 |
| [`주차_realtime_428_한계_20260803.md`](./주차_realtime_428_한계_20260803.md) | 주차 점수 금지 |
| [`충전이력_usage_희소성_과적합_20260804.md`](./충전이력_usage_희소성_과적합_20260804.md) | usage HOLD_SPARSE |
| [`핵심갭_개선계획_20260806.md`](./핵심갭_개선계획_20260806.md) | 편향·ETA·라벨 |
| [`파생변수_검토_도착라벨_20260806.md`](./파생변수_검토_도착라벨_20260806.md) | derived_v0 |
| [`최종파일명_확정_20260808.md`](./최종파일명_확정_20260808.md) | 파일명 정본 |
| [`최종패키지_명령_초안_20260806.md`](./최종패키지_명령_초안_20260806.md) | 재생성 명령 |

---

## 규칙

1. 팀에 새 자료 → **루트 최종본**만  
2. 날짜 바뀌면 전날 시리즈 → `_archive/YYYYMM/`  
3. 점수·가중치 숫자 쓰지 않기 (②)  
4. 정리: `python apps/data-pipeline/processing/tools/share/archive_team_share.py`

```
DA① | team-share final-only | {datetime.now(KST).strftime('%Y-%m-%d %H:%M')}
```
"""
    (SHARE / "README.md").write_text(readme, encoding="utf-8")

    meta = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "moved": len(moved),
        "kept_latest": kept_latest,
        "moves": moved,
    }
    (ARCHIVE / "last_archive_run.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"ok": True, "moved": len(moved), "kept_latest": kept_latest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
