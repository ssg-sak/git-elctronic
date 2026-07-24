"""Probe UTIC traffic-flow open data URL candidates.

Incident uses imsOpenData.do; traffic is documented as URL+key+IP
(not always the same public sample). Results written under docs/data/extracted/.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_PROBES

OUT = EXTRACTED_PROBES
KST = ZoneInfo("Asia/Seoul")

# Candidates commonly guessed / adjacent to UTIC open-data naming.
# Real traffic may instead be a **dedicated URL issued at application time**.
CANDIDATES = [
    "http://www.utic.go.kr/guide/nitsOpenData.do",
    "http://www.utic.go.kr/guide/trafficOpenData.do",
    "http://www.utic.go.kr/guide/trsOpenData.do",
    "http://www.utic.go.kr/guide/cttOpenData.do",
    "http://www.utic.go.kr/guide/tisOpenData.do",
    "http://www.utic.go.kr/guide/mapOpenData.do",
    "http://www.utic.go.kr/guide/getTrafficInfo.do",
    "http://www.utic.go.kr/guide/trafficInfoOpenData.do",
]


def main() -> int:
    load_dotenv(REPO / ".env")
    key = os.environ.get("UTIC_API_KEY", "").strip()
    if not key:
        raise SystemExit("UTIC_API_KEY missing")

    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    results = []
    for base in CANDIDATES:
        name = base.rsplit("/", 1)[-1]
        url = f"{base}?key={key}"
        entry = {"endpoint": base, "ok": False, "status": None, "bytes": 0, "preview": ""}
        try:
            req = Request(url, headers={"User-Agent": "EV-SafeCharge-data-pipeline/1.0"})
            with urlopen(req, timeout=45) as resp:
                body = resp.read()
                entry["ok"] = True
                entry["status"] = resp.status
                entry["bytes"] = len(body)
                entry["preview"] = body[:200].decode("utf-8", "replace")
                out = OUT / f"utic_traffic_probe_{name}_{stamp}.bin"
                out.write_bytes(body[:2_000_000])
                entry["saved"] = str(out.relative_to(REPO)).replace("\\", "/")
                print("OK", name, "bytes", len(body))
        except Exception as e:  # noqa: BLE001
            entry["error"] = f"{type(e).__name__}: {e}"
            code = getattr(e, "code", None)
            entry["status"] = code
            print("FAIL", name, code, type(e).__name__)
        results.append(entry)

    meta = {
        "probed_at": datetime.now(KST).isoformat(),
        "note": (
            "UTIC 소통은 레퍼런스상 URL+키+IP 방식. "
            "공개 샘플이 돌발(imsOpenData)과 다를 수 있음. "
            "신청 시 안내된 전용 URL이 있으면 .env UTIC_TRAFFIC_URL 로 재프로브."
        ),
        "attribution": "경찰청 도시교통정보센터(UTIC)",
        "results": results,
        "any_ok": any(r["ok"] for r in results),
    }
    meta_path = OUT / f"utic_traffic_probe_meta_{stamp}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = OUT / "utic_traffic_probe_meta_latest.json"
    latest.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("meta", meta_path)
    print("any_ok", meta["any_ok"])
    return 0 if meta["any_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
