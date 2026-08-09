"""Stamp DA① DONE banner into active data-part docs (not deep archives)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
MARKER = "<!-- DA1_DONE_BANNER_20260809 -->"
BANNER = f"""{MARKER}
> **✅ DA① 완료 (2026-08-09)** · 상태: **`DA1_READY_FOR_DA2_MODEL_EVALUATION`**  
> 수집 컷: `from_lightsail_20260809_072742` · 현재표/시간표 as_of `2026-08-09T07:23:21+09:00`  
> 조장 zip: Desktop `EV_SafeCharge_DA1to조장_풀데이터_20260809_1353.zip` · 이후 점수·추천은 **DA②**  
> 상세: [`데이터파트_①_완료상태_20260809.md`](./데이터파트_①_완료상태_20260809.md)

"""

# relative paths from REPO; banner link adjusted per location
TARGETS: list[tuple[str, str]] = [
    ("docs/README.md", "./데이터파트_①_완료상태_20260809.md"),
    ("docs/데이터파트_작업가이드.md", "./데이터파트_①_완료상태_20260809.md"),
    ("docs/데이터파트_①_완료체크.md", "./데이터파트_①_완료상태_20260809.md"),
    ("docs/데이터파트_①_8월9일까지_로드맵.md", "./데이터파트_①_완료상태_20260809.md"),
    ("docs/데이터파트_①_실행계획서.md", "./데이터파트_①_완료상태_20260809.md"),
    ("docs/데이터파트_①_8월9일까지_품질개선계획.md", "./데이터파트_①_완료상태_20260809.md"),
    ("docs/팀공유/README.md", "../데이터파트_①_완료상태_20260809.md"),
    ("docs/팀공유/최종패키지_조장전달_목록_20260809.md", "../데이터파트_①_완료상태_20260809.md"),
    ("docs/팀공유/팀공유_핸드오프_①to②_20260809.md", "../데이터파트_①_완료상태_20260809.md"),
    ("docs/팀공유/D1_KPI_핸드오프_20260809.md", "../데이터파트_①_완료상태_20260809.md"),
    ("docs/팀공유/최종패키지_명령_초안_20260806.md", "../데이터파트_①_완료상태_20260809.md"),
    ("apps/data-pipeline/AGENTS.md", "../../docs/데이터파트_①_완료상태_20260809.md"),
    ("최종본_20260809/README.md", "../docs/데이터파트_①_완료상태_20260809.md"),
]


def _banner(link: str) -> str:
    return BANNER.replace(
        "[`데이터파트_①_완료상태_20260809.md`](./데이터파트_①_완료상태_20260809.md)",
        f"[`데이터파트_①_완료상태_20260809.md`]({link})",
    )


def stamp(path: Path, link: str) -> str:
    if not path.is_file():
        return "missing"
    if path.name == "데이터파트_①_완료상태_20260809.md":
        return "skip_self"
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return "already"
    # insert after first heading line
    lines = text.splitlines(keepends=True)
    if not lines:
        return "empty"
    out: list[str] = []
    inserted = False
    for i, line in enumerate(lines):
        out.append(line)
        if not inserted and line.startswith("#"):
            # keep blank line after title if present
            out.append("\n")
            out.append(_banner(link))
            inserted = True
    if not inserted:
        out.insert(0, _banner(link) + "\n")
    path.write_text("".join(out), encoding="utf-8")
    return "stamped"


def stamp_dir(dir_path: Path, link: str) -> list[tuple[str, str]]:
    results = []
    if not dir_path.is_dir():
        return results
    for p in sorted(dir_path.glob("*.md")):
        results.append((str(p.relative_to(REPO)).replace("\\", "/"), stamp(p, link)))
    return results


def main() -> None:
    results: list[tuple[str, str]] = []
    for rel, link in TARGETS:
        p = REPO / rel
        results.append((rel, stamp(p, link)))

    # 최종본 00_먼저읽기 전부
    results.extend(
        stamp_dir(
            REPO / "최종본_20260809" / "00_먼저읽기",
            "../../../docs/데이터파트_①_완료상태_20260809.md",
        )
    )

    # copy status into final pack
    src = REPO / "docs" / "데이터파트_①_완료상태_20260809.md"
    dst = REPO / "최종본_20260809" / "00_먼저읽기" / "데이터파트_①_완료상태_20260809.md"
    if src.is_file() and dst.parent.is_dir():
        body = src.read_text(encoding="utf-8")
        if MARKER not in body:
            # status file itself starts with H1 — prepend note
            pass
        dst.write_text(body, encoding="utf-8")
        results.append((str(dst.relative_to(REPO)).replace("\\", "/"), "copied"))

    for rel, st in results:
        print(f"{st:12} {rel}")


if __name__ == "__main__":
    main()
