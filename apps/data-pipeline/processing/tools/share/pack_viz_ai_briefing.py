"""Build AI-explainable visualization pack + Desktop zip.

Output:
  docs/팀공유/시각자료_AI해설팩_20260808/
  Desktop/EV_SafeCharge_시각자료_AI해설팩_20260808.zip
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
SHARE = REPO / "docs" / "팀공유"
STAMP = "20260808"
OUT = SHARE / f"시각자료_AI해설팩_{STAMP}"
DESK = Path.home() / "Desktop"
KST = ZoneInfo("Asia/Seoul")

# (section_dir, source_relative_to_SHARE_or_absolute_hint, label)
# Sources are resolved under SHARE unless they start with docs/
SOURCES: list[tuple[str, str, str]] = [
    ("01_EDA", "EDA_최종_20260808/figures", "EDA 최종"),
    ("02_상태수집_패널", "상태수집_패널차트_20260808/figures", "상태수집 패널"),
    ("03_시간대_가용률", "시간대_가용률_20260808/figures", "시간대 가용률"),
    ("04_현재표_의미", "D1_최신화의미_20260808", "현재표 의미"),
    ("05_도시혼잡", "도시혼잡_시계열_20260808/figures", "도시 혼잡"),
    ("06_돌발_UTIC", "돌발_UTIC_분석_20260808", "UTIC 돌발"),
    ("07_HGB_피처선정", "피처선정_최종_HGB_도착ETA_20260808", "HGB 피처선정 BI"),
    ("08_과적합위험", "과적합위험_HGB_도착ETA_20260808", "과적합 위험"),
    ("09_ETA_보정샘플", "ETA_보정샘플_20260806/figures", "ETA 보정 샘플"),
    ("10_IQR_이상치", "IQR_이상치검사_20260806", "IQR 이상치"),
    ("11_차트유형_갤러리", "차트유형_갤러리_20260806", "차트 유형 갤러리"),
    ("12_시각화팩_통합", "시각화팩_통합_20260808", "통합 시각화팩(보조)"),
]

DOCS_COPY = [
    ("이름_쉬운말_안내_20260808.md", "00_브리핑/이름_쉬운말_안내_20260808.md"),
    ("EDA_KPI_보고서_20260808.md", "00_브리핑/EDA_KPI_보고서_20260808.md"),
    ("ETA_동대구고정_한계_조장필독_20260808.md", "00_브리핑/ETA_동대구고정_한계_조장필독_20260808.md"),
    ("주차_realtime_428_한계_20260803.md", "00_브리핑/주차_realtime_428_한계_20260803.md"),
    ("충전이력_usage_희소성_과적합_20260804.md", "00_브리핑/충전이력_usage_희소성_과적합_20260804.md"),
    ("모델적합도_과적합_완료패키지_20260808.md", "00_브리핑/모델적합도_과적합_완료패키지_20260808.md"),
    ("시각자료_해석설명서_20260731.md", "00_브리핑/시각자료_해석설명서_20260731.md"),
    ("시간대_가용률_평균중앙값_해설_20260731.md", "00_브리핑/시간대_가용률_평균중앙값_해설_20260731.md"),
]

IMG_SUFFIX = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _resolve(src: str) -> Path:
    p = SHARE / src
    if p.exists():
        return p
    # try figures parent if path is a dir with nested figures
    return p


def _iter_images(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file() and root.suffix.lower() in IMG_SUFFIX:
        return [root]
    out: list[Path] = []
    # prefer figures/ first then all
    fig = root / "figures" if root.is_dir() else None
    search_roots = [fig] if fig and fig.is_dir() else [root]
    if root.is_dir() and (not fig or not fig.is_dir()):
        search_roots = [root]
    elif root.is_dir() and fig and fig.is_dir():
        # also include root-level pngs outside figures
        search_roots = [fig, root]
    seen: set[Path] = set()
    for sr in search_roots:
        if sr is None or not sr.exists():
            continue
        if sr.is_file():
            files = [sr]
        else:
            files = sorted(sr.rglob("*"))
        for f in files:
            if not f.is_file() or f.suffix.lower() not in IMG_SUFFIX:
                continue
            if f in seen:
                continue
            # skip if under another figures when already taken from figures - ok
            seen.add(f)
            out.append(f)
    return out


def _copy_section(section: str, src_rel: str, label: str) -> list[dict]:
    src = _resolve(src_rel)
    dest = OUT / section
    dest.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    images = _iter_images(src)
    # dedupe by name preferring shorter path / figures
    by_name: dict[str, Path] = {}
    for img in images:
        # skip nested copies from 시각화팩 that duplicate if name collision — keep first
        name = img.name
        if name in by_name:
            continue
        by_name[name] = img
    for i, (name, img) in enumerate(sorted(by_name.items()), start=1):
        # avoid overwrite: unique name if needed
        out_name = name
        target = dest / out_name
        if target.exists():
            out_name = f"{img.stem}_{i}{img.suffix}"
            target = dest / out_name
        shutil.copy2(img, target)
        vid = f"{section.split('_')[0]}-{i:02d}"
        rows.append(
            {
                "id": vid,
                "section": section,
                "label": label,
                "file": f"{section}/{out_name}",
                "src": str(img.relative_to(REPO)).replace("\\", "/"),
            }
        )
    return rows


def _write_briefing(index_rows: list[dict]) -> None:
    # group by section
    by_sec: dict[str, list[dict]] = {}
    for r in index_rows:
        by_sec.setdefault(r["section"], []).append(r)

    lines = [
        "# 시각자료 AI 해설 브리핑 — 2026-08-08",
        "",
        "> Gemini Deep Think / ChatGPT / Claude에 **이 폴더 전체**를 넣고 아래 프롬프트로 설명시키면 된다.",
        f"> 생성: {datetime.now(KST).isoformat(timespec='seconds')}",
        "",
        "---",
        "",
        "## A. AI에게 먼저 넣을 고정 프롬프트 (복붙)",
        "",
        "```text",
        "너는 EV SafeCharge 데이터파트(①)의 시각자료 해설자다.",
        "역할: 첨부된 차트/대시보드를 비전문가(조장·팀원)가 이해하도록 쉬운 말로 설명한다.",
        "데이터 담당은 표·품질·EDA까지다. 추천 점수·랭킹·가중치 숫자는 만들지 않는다.",
        "",
        "필수 용어:",
        "- 현재표 = 지금 시각 기준 충전소 1행 요약 (예전 D1)",
        "- 시간표 = 충전소×시간 상태 이력 (예전 D2)",
        "- as_of = 현재표를 찍은 기준시각",
        "- CHECK = 상태 갱신이 15분 넘음 (파이프라인 고장 단정 금지)",
        "",
        "규칙:",
        "1) 첨부 문서의 숫자·파일명·한계만 사용. 모르는 숫자는 “문서에 없음”이라고 한다.",
        "2) 차트에서 보이는 패턴은 말해도 되지만, 인과를 단정하지 않는다 (“경향/가능”으로).",
        "3) 주차·usage·동대구 고정 ETA는 00_브리핑 한계 문서를 반드시 고지한다.",
        "4) 출력 형식은 항상:",
        "   - 한 줄 결론",
        "   - 이 그림이 보여주는 것 (3~5줄)",
        "   - 숫자/구간 (문서 기준)",
        "   - 오해하기 쉬운 점",
        "   - 조장/②가 다음으로 볼 것",
        "5) 한국어, 쉬운 말. 점수·모델 성능을 지어내지 말 것.",
        "6) 그림 파일명과 아래 인덱스의 id를 먼저 맞춘 뒤 설명한다.",
        "```",
        "",
        "---",
        "",
        "## B. 프로젝트 한 줄",
        "",
        "사용자가 충전소에 **도착했을 때 실제로 충전할 가능성이 높은** 소를 고르기 위한 데이터 작업.",
        "이 팩의 그림은 **표·품질·패턴 설명**용이다. **추천 점수는 없음 (② 영역).**",
        "",
        "---",
        "",
        "## C. 컷오프·정본 숫자 (0808)",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        "| 현재표 as_of | 2026-08-08T11:17:46+09:00 |",
        "| 시간표 | 약 867만 행 · 07-17 ~ 08-08 11:17 |",
        "| KPI | OK 9/12 · K3 UTIC FAIL · K8 신선도 WARN · K9 mock WARN |",
        "| EDA E1 | 가장 빔 11시 · 가장 참 22시 · 오전0.79 / 저녁0.69 |",
        "| EDA E2 | 평일0.72 / 주말0.70 · **잠정** |",
        "| E4 신선도 | HIGH193 · NORMAL269 · CHECK3193 · 미관측555 |",
        "",
        "자세한 표 → `00_브리핑/EDA_KPI_보고서_20260808.md`",
        "",
        "---",
        "",
        "## D. 자주 나오는 오해 (반드시)",
        "",
        "1. CHECK 많음 ≠ 파이프라인 고장 (상태 API 갱신이 느린 소가 많음)",
        "2. 평균 ≠ 중앙값 (`시간대_가용률_평균중앙값_해설`)",
        "3. 동대구 ETA = **학습·오프라인용 고정 출발지** (서빙은 사용자 위치 TMAP)",
        "4. 주차 realtime 붙은 소 제한 → **주차 점수 금지**",
        "5. usage 이력 희소 → 과적합 위험 · HOLD",
        "6. 요일 EDA는 provisional (규칙으로 못 박지 않음)",
        "",
        "---",
        "",
        "## E. 폴더 안내",
        "",
        "| 폴더 | 내용 |",
        "|---|---|",
        "| `00_브리핑/` | 이 문서 + KPI/EDA/한계 md |",
        "| `01_EDA` ~ `11_…` | 주제별 그림 |",
        "| `12_시각화팩_통합` | 통합팩 복사(중복 가능, 보조) |",
        "",
        "---",
        "",
        "## F. 그림 인덱스",
        "",
        "| ID | 섹션 | 파일 | 한 줄(추정 용도) |",
        "|---|---|---|---|",
    ]

    section_hints = {
        "01_EDA": "시간대·신뢰도·혼잡 보조 EDA",
        "02_상태수집_패널": "상태 수집 볼륨·시간대·bias",
        "03_시간대_가용률": "가용률 시계열·히트맵·등급",
        "04_현재표_의미": "현재표 숫자 의미",
        "05_도시혼잡": "도시 혼잡 vs 가용",
        "06_돌발_UTIC": "돌발(UTIC) 분포",
        "07_HGB_피처선정": "최종 피처 선정 BI",
        "08_과적합위험": "과적합 위험 진단",
        "09_ETA_보정샘플": "ETA 보정 샘플",
        "10_IQR_이상치": "IQR 이상치 검사",
        "11_차트유형_갤러리": "차트 유형 참고",
        "12_시각화팩_통합": "통합 시각화 보조",
    }

    for r in index_rows:
        hint = section_hints.get(r["section"], r["label"])
        lines.append(f"| `{r['id']}` | {r['section']} | `{r['file']}` | {hint} |")

    lines += [
        "",
        f"**그림 총 {len(index_rows)}장**",
        "",
        "---",
        "",
        "## G. 시킬 작업 모드",
        "",
        "### 모드1 — 전체 투어",
        "```text",
        "00_브리핑/시각자료_AI해설_브리핑.md 와 그림 인덱스를 기준으로 모드1 실행.",
        "섹션 01→11 순서대로, 각 그림마다 지정 출력 형식만 사용.",
        "12_시각화팩_통합은 앞 섹션과 중복이면 ‘앞에서 설명함’으로 짧게.",
        "마지막에 ‘조장이 오늘 기억할 문장 5개’로 끝낸다.",
        "```",
        "",
        "### 모드2 — 3분 발표",
        "```text",
        "비전공 팀원용 3분 발표 대본. 현재표/시간표 용어만.",
        "KPI FAIL/WARN과 EDA 한 줄만. 점수는 언급 금지.",
        "```",
        "",
        "### 모드3 — 환각 검사",
        "```text",
        "네 설명을 브리핑·EDA_KPI 문서와 대조해 환각 검사해라.",
        "문서에 없는 숫자·인과·점수 주장을 bullet로 나열. 없으면 ‘없음’.",
        "```",
        "",
        "### 모드4 — 특정 그림",
        "```text",
        "인덱스 ID Vxx (또는 파일명)만 딥다이브. 형식 동일.",
        "```",
        "",
        "---",
        "",
        "## H. 업로드 순서 추천",
        "",
        "1. `00_브리핑/시각자료_AI해설_브리핑.md` (이 파일)",
        "2. `00_브리핑/EDA_KPI_보고서_20260808.md`",
        "3. `00_브리핑/ETA_동대구고정_한계_조장필독_20260808.md`",
        "4. 그림 폴더 `01_` ~ `08_` (필요 시 나머지)",
        "5. 모드1 지시문",
        "",
        "```",
        "DA① | viz AI briefing pack | 20260808",
        "```",
        "",
    ]
    briefing = OUT / "00_브리핑" / "시각자료_AI해설_브리핑.md"
    briefing.parent.mkdir(parents=True, exist_ok=True)
    briefing.write_text("\n".join(lines), encoding="utf-8")
    # also root README pointer
    (OUT / "README_먼저읽기.md").write_text(
        "\n".join(
            [
                "# 시각자료 AI 해설팩 — 먼저 읽기",
                "",
                "1. `00_브리핑/시각자료_AI해설_브리핑.md` 를 연다",
                "2. 안의 **고정 프롬프트**를 Gemini/ChatGPT/Claude에 붙인다",
                "3. 이 zip(또는 폴더) 전체를 첨부한다",
                "4. **모드1** 지시문을 실행한다",
                "",
                "점수·추천 순위는 이 팩에 없다.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # docs
    for src_name, dest_rel in DOCS_COPY:
        src = SHARE / src_name
        if not src.exists():
            continue
        dest = OUT / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    index_rows: list[dict] = []
    missing: list[str] = []
    for section, src_rel, label in SOURCES:
        src = _resolve(src_rel)
        if not src.exists():
            missing.append(src_rel)
            continue
        # for 시각화팩_통합 — copy only figures subdirs to avoid huge nested readme noise
        if section.startswith("12_"):
            # flatten pngs from pack sections
            dest = OUT / section
            dest.mkdir(parents=True, exist_ok=True)
            n = 0
            for img in sorted(src.rglob("*.png")):
                # skip if path too deep duplicates - take all unique names with prefix
                rel = img.relative_to(src)
                out_name = "__".join(rel.parts)
                shutil.copy2(img, dest / out_name)
                n += 1
                index_rows.append(
                    {
                        "id": f"12-{n:02d}",
                        "section": section,
                        "label": label,
                        "file": f"{section}/{out_name}",
                        "src": str(img.relative_to(REPO)).replace("\\", "/"),
                    }
                )
            continue
        index_rows.extend(_copy_section(section, src_rel, label))

    _write_briefing(index_rows)

    meta = {
        "stamp": STAMP,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "n_images": len(index_rows),
        "missing": missing,
        "out": str(OUT.relative_to(REPO)).replace("\\", "/"),
    }
    (OUT / "pack_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "00_브리핑" / "그림_인덱스.json").write_text(
        json.dumps(index_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Desktop folder + zip
    desk_dir = DESK / f"EV_SafeCharge_시각자료_AI해설팩_{STAMP}"
    if desk_dir.exists():
        shutil.rmtree(desk_dir)
    shutil.copytree(OUT, desk_dir)

    zip_path = DESK / f"EV_SafeCharge_시각자료_AI해설팩_{STAMP}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in desk_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(desk_dir.parent))

    print(
        json.dumps(
            {
                "ok": True,
                "out": str(OUT),
                "desktop_folder": str(desk_dir),
                "desktop_zip": str(zip_path),
                "n_images": len(index_rows),
                "zip_mb": round(zip_path.stat().st_size / (1024 * 1024), 2),
                "missing": missing,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
