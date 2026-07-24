"""결측치 현황 조사 (Data Profiling) — 1단계
수집된 원본 DB(collection.db)를 읽어 테이블별 결측치 현황을 출력한다.
수집기 실행 전이면 DB 파일이 없을 수 있으므로 파일 존재 여부를 먼저 확인한다.

단독 실행: python profiling.py
단독 실행 (출력 저장): python profiling.py > profiling_report.txt
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
# processing/  →  collection/data/collection.db
import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import DATA_PIPELINE

COLLECTION_DIR = DATA_PIPELINE / "collection"
DB_PATH = COLLECTION_DIR / "data" / "collection.db"


# ── 유틸리티 ──────────────────────────────────────────────────────────────────
def _pct(part: int, total: int) -> str:
    """결측치 비율 문자열 반환."""
    if total == 0:
        return "N/A"
    return f"{part / total * 100:.1f}%"


def _section(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _row(label: str, missing: int, total: int) -> None:
    bar_width = 20
    filled = int(missing / total * bar_width) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    print(f"  {label:<28} [{bar}] {missing:>5}건 / {_pct(missing, total)}")


# ── 테이블 존재 여부 확인 ─────────────────────────────────────────────────────
def _get_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


# ── 1. charging_stations 결측치 분석 ─────────────────────────────────────────
def profile_charging_stations(conn: sqlite3.Connection) -> dict:
    _section("1. charging_stations (충전소 정보)")

    total = conn.execute("SELECT COUNT(*) FROM charging_stations").fetchone()[0]
    print(f"  전체 레코드 수: {total:,}건")

    if total == 0:
        print("  ⚠️  데이터 없음 — 수집기를 먼저 실행해 주세요.")
        return {"total": 0}

    checks = {
        "lat (위도) 누락/0":
            "lat IS NULL OR lat = 0.0",
        "lng (경도) 누락/0":
            "lng IS NULL OR lng = 0.0",
        "위경도 동시 누락":
            "(lat IS NULL OR lat = 0.0) AND (lng IS NULL OR lng = 0.0)",
        "addr (주소) 누락":
            "addr IS NULL OR trim(addr) = ''",
        "stat_nm (충전소명) 누락":
            "stat_nm IS NULL OR trim(stat_nm) = ''",
        "use_time (이용시간) 누락":
            "use_time IS NULL OR trim(use_time) = ''",
        "parking_free (주차무료) 누락":
            "parking_free IS NULL OR trim(parking_free) = ''",
        "busi_nm (운영기관) 누락":
            "busi_nm IS NULL OR trim(busi_nm) = ''",
    }

    print()
    results = {"total": total}
    for label, cond in checks.items():
        cnt = conn.execute(
            f"SELECT COUNT(*) FROM charging_stations WHERE {cond}"
        ).fetchone()[0]
        _row(label, cnt, total)
        results[label] = cnt

    # 대구 범위 벗어난 좌표 (위도 35.6~36.2, 경도 128.3~128.9)
    out_of_range = conn.execute(
        """SELECT COUNT(*) FROM charging_stations
           WHERE lat IS NOT NULL AND lat != 0.0
             AND (lat < 35.6 OR lat > 36.2 OR lng < 128.3 OR lng > 128.9)"""
    ).fetchone()[0]
    _row("좌표 대구 범위 이탈", out_of_range, total)
    results["좌표 대구 범위 이탈"] = out_of_range

    return results


# ── 2. chargers 결측치 분석 ──────────────────────────────────────────────────
def profile_chargers(conn: sqlite3.Connection) -> dict:
    _section("2. chargers (충전기 상태)")

    total = conn.execute("SELECT COUNT(*) FROM chargers").fetchone()[0]
    print(f"  전체 레코드 수: {total:,}건")

    if total == 0:
        print("  ⚠️  데이터 없음 — 수집기를 먼저 실행해 주세요.")
        return {"total": 0}

    checks = {
        "chger_type (충전기 타입) 누락":
            "chger_type IS NULL OR trim(chger_type) = ''",
        "output (충전 용량) 누락":
            "output IS NULL OR trim(output) = ''",
        "stat (상태 코드) 누락":
            "stat IS NULL OR trim(stat) = ''",
        "stat_updated_at (갱신시각) 누락":
            "stat_updated_at IS NULL OR trim(stat_updated_at) = ''",
        "stat_nm (상태명) 누락":
            "stat_nm IS NULL OR trim(stat_nm) = ''",
    }

    print()
    results = {"total": total}
    for label, cond in checks.items():
        cnt = conn.execute(
            f"SELECT COUNT(*) FROM chargers WHERE {cond}"
        ).fetchone()[0]
        _row(label, cnt, total)
        results[label] = cnt

    # 충전기 타입 코드별 분포
    _section("2-1. 충전기 타입(chger_type) 코드 분포")
    type_rows = conn.execute(
        """SELECT chger_type, COUNT(*) AS cnt
           FROM chargers
           GROUP BY chger_type
           ORDER BY cnt DESC"""
    ).fetchall()
    CHGER_TYPE_MAP = {
        "01": "DC차데모",        "02": "AC완속",
        "03": "DC차데모+AC3상",  "04": "DC콤보",
        "05": "DC차데모+DC콤보", "06": "DC차데모+AC3상+DC콤보",
        "07": "AC3상",           "08": "DC콤보(완속)",
        "09": "H2(수소)",        "10": "초급속(멀티)",
        "11": "초급속(미확인규격)",
    }
    print(f"  {'코드':<6} {'표준명':<22} {'건수':>8}")
    print(f"  {'-'*6} {'-'*22} {'-'*8}")
    for code, cnt in type_rows:
        name = CHGER_TYPE_MAP.get(str(code), "알 수 없음") if code else "(NULL)"
        print(f"  {str(code or 'NULL'):<6} {name:<22} {cnt:>8,}건")

    # 상태 코드 분포
    _section("2-2. 충전기 상태(stat) 코드 분포")
    STAT_MAP = {
        "1": "통신이상→미확인", "2": "이용가능", "3": "충전중",
        "4": "운영중지→고장", "5": "점검중", "9": "상태미확인",
    }
    stat_rows = conn.execute(
        """SELECT stat, COUNT(*) AS cnt
           FROM chargers
           GROUP BY stat
           ORDER BY cnt DESC"""
    ).fetchall()
    print(f"  {'코드':<6} {'표준명':<16} {'건수':>8}")
    print(f"  {'-'*6} {'-'*16} {'-'*8}")
    for code, cnt in stat_rows:
        name = STAT_MAP.get(str(code), "알 수 없음") if code else "(NULL)"
        print(f"  {str(code or 'NULL'):<6} {name:<16} {cnt:>8,}건")

    return results


# ── 3. stat_updated_at 신뢰도 분포 (데이터가 있을 때만) ──────────────────────
def profile_reliability(conn: sqlite3.Connection) -> None:
    _section("3. stat_updated_at 기준 신뢰도 예비 분포")

    total = conn.execute(
        "SELECT COUNT(*) FROM chargers WHERE stat_updated_at IS NOT NULL AND stat_updated_at != ''"
    ).fetchone()[0]

    if total == 0:
        print("  ⚠️  stat_updated_at 데이터 없음 — 수집 후 재실행 필요.")
        return

    now_iso = datetime.now().strftime("%Y%m%d%H%M%S")
    # SQLite에서 분 차이 계산 (statUpdDt 포맷: YYYYMMDDHHmmss)
    high = conn.execute(
        f"""SELECT COUNT(*) FROM chargers
            WHERE stat_updated_at IS NOT NULL AND length(stat_updated_at) = 14
            AND (CAST(strftime('%s','now') AS INTEGER)
                 - CAST(strftime('%s', substr(stat_updated_at,1,4)||'-'||
                                          substr(stat_updated_at,5,2)||'-'||
                                          substr(stat_updated_at,7,2)||'T'||
                                          substr(stat_updated_at,9,2)||':'||
                                          substr(stat_updated_at,11,2)||':'||
                                          substr(stat_updated_at,13,2)) AS INTEGER)) <= 300"""
    ).fetchone()[0]

    normal = conn.execute(
        f"""SELECT COUNT(*) FROM chargers
            WHERE stat_updated_at IS NOT NULL AND length(stat_updated_at) = 14
            AND (CAST(strftime('%s','now') AS INTEGER)
                 - CAST(strftime('%s', substr(stat_updated_at,1,4)||'-'||
                                          substr(stat_updated_at,5,2)||'-'||
                                          substr(stat_updated_at,7,2)||'T'||
                                          substr(stat_updated_at,9,2)||':'||
                                          substr(stat_updated_at,11,2)||':'||
                                          substr(stat_updated_at,13,2)) AS INTEGER)) BETWEEN 301 AND 900"""
    ).fetchone()[0]

    check_required = conn.execute(
        f"""SELECT COUNT(*) FROM chargers
            WHERE stat_updated_at IS NOT NULL AND length(stat_updated_at) = 14
            AND (CAST(strftime('%s','now') AS INTEGER)
                 - CAST(strftime('%s', substr(stat_updated_at,1,4)||'-'||
                                          substr(stat_updated_at,5,2)||'-'||
                                          substr(stat_updated_at,7,2)||'T'||
                                          substr(stat_updated_at,9,2)||':'||
                                          substr(stat_updated_at,11,2)||':'||
                                          substr(stat_updated_at,13,2)) AS INTEGER)) > 900"""
    ).fetchone()[0]

    print(f"  (갱신시각 존재하는 레코드 기준: {total:,}건)")
    print()
    _row("🟢 높음  (5분 이내)",  high,           total)
    _row("🟡 보통  (5~15분)",   normal,         total)
    _row("🔴 확인필요 (15분+)", check_required, total)


# ── 4. 종합 요약 ──────────────────────────────────────────────────────────────
def summary(station_result: dict, charger_result: dict) -> None:
    _section("4. 종합 요약 및 다음 단계 권고")

    s_total = station_result.get("total", 0)
    c_total = charger_result.get("total", 0)

    if s_total == 0 or c_total == 0:
        print("  ⚠️  수집된 데이터가 없습니다.")
        print()
        print("  다음 단계:")
        print("    1) git-elctronic/ 루트에 .env 파일 생성 (API 키 설정)")
        print("    2) python apps/data-pipeline/collection/ev_charger_info.py 실행")
        print("    3) python apps/data-pipeline/processing/profiling.py 재실행")
        return

    coord_missing   = station_result.get("위경도 동시 누락", 0)
    addr_missing    = station_result.get("addr (주소) 누락", 0)
    type_missing    = charger_result.get("chger_type (충전기 타입) 누락", 0)
    stat_missing    = charger_result.get("stat (상태 코드) 누락", 0)
    updated_missing = charger_result.get("stat_updated_at (갱신시각) 누락", 0)

    print(f"  충전소 {s_total:,}곳 / 충전기 {c_total:,}대 분석 완료")
    print()
    print("  처리 우선순위:")

    priority = []
    if coord_missing > 0:
        priority.append(
            f"  1순위 (위경도 누락) — {coord_missing}건 → 카카오 지오코딩으로 복원 필요"
        )
    if addr_missing > 0:
        priority.append(
            f"  2순위 (주소 누락) — {addr_missing}건 → 역지오코딩 또는 DROP 처리 필요"
        )
    if type_missing > 0:
        priority.append(
            f"  3순위 (충전기 타입 누락) — {type_missing}건 → 기본값 '알 수 없음' 매핑"
        )
    if stat_missing > 0:
        priority.append(
            f"  4순위 (상태 코드 누락) — {stat_missing}건 → 코드 '9'(상태미확인) 적용"
        )
    if updated_missing > 0:
        priority.append(
            f"  5순위 (갱신시각 누락) — {updated_missing}건 → fetched_at 대체 + 신뢰도 최하위 강제 부여"
        )

    if priority:
        for p in priority:
            print(p)
    else:
        print("  ✅ 주요 결측치 없음 — cleansing.py 로 2단계 진행 가능")


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"\n{'━'*60}")
    print(f"  데이터 가공 1단계 — 결측치 프로파일링 리포트")
    print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  대상 DB  : {DB_PATH}")
    print(f"{'━'*60}")

    if not DB_PATH.exists():
        print()
        print(f"  ❌ DB 파일을 찾을 수 없습니다: {DB_PATH}")
        print()
        print("  해결 방법:")
        print("    1) git-elctronic/ 루트에 .env 파일 생성")
        print("       (DATA_GO_KR_KEY, KAKAO_REST_KEY 필수)")
        print("    2) 아래 수집기를 실행해 DB 초기화 및 데이터 수집:")
        print("       cd apps/data-pipeline/collection")
        print("       python ev_charger_info.py")
        print()
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tables = _get_tables(conn)
    print(f"\n  DB 내 테이블: {tables}")

    station_result = {}
    charger_result = {}

    if "charging_stations" in tables:
        station_result = profile_charging_stations(conn)
    else:
        print("\n  ⚠️  charging_stations 테이블 없음")

    if "chargers" in tables:
        charger_result = profile_chargers(conn)
        profile_reliability(conn)
    else:
        print("\n  ⚠️  chargers 테이블 없음")

    summary(station_result, charger_result)

    conn.close()
    print(f"\n{'━'*60}\n")


if __name__ == "__main__":
    main()
