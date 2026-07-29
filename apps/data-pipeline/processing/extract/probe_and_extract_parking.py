"""Probe parking APIs and extract Daegu rows when available.

Sources:
  - KOTSA B553881 Parking (PrkSttusInfo / PrkOprInfo / PrkRealtimeInfo)
  - National standard tn_pubr_prkplce_info_api (15012896)
  - Daegu PIS (if real keys)

Usage (repo root):
  python apps/data-pipeline/processing/extract/probe_and_extract_parking.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_PARKING

KST = ZoneInfo("Asia/Seoul")
OUT_PROBE = REPO / "docs" / "data" / "analysis" / "parking"
DAEGU_LAT = (35.6, 36.05)
DAEGU_LNG = (128.35, 128.85)

KOTSA = {
    "PrkSttusInfo": "http://apis.data.go.kr/B553881/Parking/PrkSttusInfo",
    "PrkOprInfo": "http://apis.data.go.kr/B553881/Parking/PrkOprInfo",
    "PrkRealtimeInfo": "http://apis.data.go.kr/B553881/Parking/PrkRealtimeInfo",
}
NATIONAL = "https://api.data.go.kr/openapi/tn_pubr_prkplce_info_api"
PIS_INFO = "https://pis.daegu.go.kr/api/serviceApply/prkInfo"
PIS_RT = "https://pis.daegu.go.kr/api/serviceApply/rltmPrkInfo"


def _key_meta(name: str, val: str) -> str:
    v = (val or "").strip()
    if not v:
        return "MISSING"
    if "MOCK" in v.upper():
        return "MOCK"
    return f"SET(len={len(v)})"


def _get(url: str, params: dict[str, str] | None = None, headers: dict | None = None, timeout: int = 60) -> tuple[int, str, bytes]:
    if params:
        # serviceKey often already percent-encoded from portal
        q = urlencode(params, doseq=True, safe="%")
        url = f"{url}?{q}"
    req = Request(url, headers=headers or {"User-Agent": "EV-SafeCharge-parking-probe/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, ctype, body
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).encode("utf-8", errors="replace")
        return 0, "error", msg


def _sniff(body: bytes) -> str:
    head = body[:200].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        return "html"
    if head.startswith(b"{") or head.startswith(b"["):
        return "json"
    if head.startswith(b"<?xml") or head.startswith(b"<response") or head.startswith(b"<OpenAPI"):
        return "xml"
    return "other"


def _parse_json(body: bytes) -> Any:
    return json.loads(body.decode("utf-8", errors="replace"))


def probe_kotsa(key: str) -> list[dict]:
    out = []
    for name, url in KOTSA.items():
        # try JSON format=2 first, then XML format=1
        best: dict[str, Any] = {"name": f"kotsa_{name}"}
        for fmt in ("2", "1"):
            status, ctype, body = _get(
                url,
                {
                    "serviceKey": key,
                    "pageNo": "1",
                    "numOfRows": "10",
                    "format": fmt,
                },
            )
            sniff = _sniff(body)
            entry = {
                "name": f"kotsa_{name}",
                "http": status,
                "ctype": ctype,
                "sniff": sniff,
                "format": fmt,
                "head": body[:180].decode("utf-8", errors="replace").replace("\n", " ")[:180],
            }
            if sniff == "json":
                try:
                    data = _parse_json(body)
                    entry["json_keys"] = list(data.keys())[:12] if isinstance(data, dict) else type(data).__name__
                    # common wrappers
                    rc = None
                    if isinstance(data, dict):
                        rc = (
                            data.get("resultCode")
                            or (data.get("header") or {}).get("resultCode")
                            or (data.get("response") or {}).get("header", {}).get("resultCode")
                        )
                        entry["resultCode"] = rc
                        entry["resultMsg"] = (
                            data.get("resultMsg")
                            or (data.get("header") or {}).get("resultMsg")
                            or (data.get("response") or {}).get("header", {}).get("resultMsg")
                        )
                    if sniff == "json" and status == 200 and rc in (None, "00", "0", 0):
                        entry["ok_candidate"] = True
                        best = entry
                        break
                except Exception as exc:  # noqa: BLE001
                    entry["parse_err"] = str(exc)
            elif sniff == "xml" and status == 200:
                try:
                    root = ET.fromstring(body)
                    rc = root.findtext(".//resultCode") or root.findtext(".//header/resultCode")
                    entry["resultCode"] = rc
                    entry["resultMsg"] = root.findtext(".//resultMsg") or root.findtext(".//header/resultMsg")
                    if rc in ("00", "0", None):
                        entry["ok_candidate"] = True
                        best = entry
                        break
                except Exception as exc:  # noqa: BLE001
                    entry["parse_err"] = str(exc)
            best = entry
        out.append(best)
    return out


def probe_national(key: str) -> dict:
    status, ctype, body = _get(
        NATIONAL,
        {
            "serviceKey": key,
            "pageNo": "1",
            "numOfRows": "10",
            "type": "json",
            "instt_nm": "대구광역시",
        },
    )
    sniff = _sniff(body)
    entry: dict[str, Any] = {
        "name": "national_standard",
        "http": status,
        "ctype": ctype,
        "sniff": sniff,
        "head": body[:220].decode("utf-8", errors="replace").replace("\n", " ")[:220],
    }
    if sniff == "json":
        try:
            data = _parse_json(body)
            # shapes vary: {response:{header,body}} or {header,body} or {resultCode}
            header = data.get("response", {}).get("header") if isinstance(data, dict) else None
            if not header and isinstance(data, dict):
                header = data.get("header") or data
            if isinstance(header, dict):
                entry["resultCode"] = header.get("resultCode") or header.get("RESULT_CODE")
                entry["resultMsg"] = header.get("resultMsg") or header.get("RESULT_MSG")
            body_obj = None
            if isinstance(data, dict):
                body_obj = (data.get("response") or {}).get("body") or data.get("body")
            if isinstance(body_obj, dict):
                items = body_obj.get("items") or body_obj.get("item")
                entry["totalCount"] = body_obj.get("totalCount")
                if isinstance(items, list):
                    entry["sample_n"] = len(items)
                elif isinstance(items, dict):
                    entry["sample_n"] = 1
            entry["ok_candidate"] = entry.get("resultCode") in ("00", "0", 0, None) and status == 200 and sniff == "json"
            # resultCode 00 with empty is still ok
            if entry.get("resultCode") in ("00", "0", 0):
                entry["ok_candidate"] = True
        except Exception as exc:  # noqa: BLE001
            entry["parse_err"] = str(exc)
    return entry


def probe_pis(info_key: str, rt_key: str) -> list[dict]:
    out = []
    for name, url, key in (
        ("pis_prkInfo", PIS_INFO, info_key),
        ("pis_rltm", PIS_RT, rt_key),
    ):
        if not key or "MOCK" in key.upper():
            out.append({"name": name, "http": None, "skipped": "MOCK_or_missing"})
            continue
        status, ctype, body = _get(url, {"serviceKey": key} if False else None, headers={"Authorization": key} if False else {})
        # PIS typically uses query apiKey
        status, ctype, body = _get(url, {"apiKey": key})
        out.append(
            {
                "name": name,
                "http": status,
                "ctype": ctype,
                "sniff": _sniff(body),
                "head": body[:180].decode("utf-8", errors="replace").replace("\n", " ")[:180],
            }
        )
    return out


def _in_daegu(lat: float | None, lng: float | None, addr: str) -> bool:
    if lat is not None and lng is not None:
        if DAEGU_LAT[0] <= lat <= DAEGU_LAT[1] and DAEGU_LNG[0] <= lng <= DAEGU_LNG[1]:
            return True
    a = addr or ""
    return "대구" in a


def _is_kotsa_daegu(item: dict) -> bool:
    """Use KOTSA's administrative-region field, not a broad coordinate box."""
    sido = str(item.get("prk_plce_adres_sido") or "").strip()
    addr = str(item.get("prk_plce_adres") or "").strip()
    return sido == "대구광역시" or addr.startswith("대구광역시")


def _dedupe_kotsa_csv(path: Path) -> int:
    """Deduplicate a completed/resumed KOTSA extract by its source identifier."""
    deduped = path.with_suffix(".dedup")
    seen: set[str] = set()
    kept = 0
    with (
        path.open(encoding="utf-8-sig", newline="") as source,
        deduped.open("w", encoding="utf-8-sig", newline="") as target,
    ):
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise RuntimeError(f"KOTSA extract has no header: {path}")
        writer = csv.DictWriter(target, fieldnames=reader.fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            source_id = str(row.get("prk_center_id") or "").strip()
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            writer.writerow(row)
            kept += 1
    deduped.replace(path)
    return kept


def extract_national_daegu(key: str, stamp: str) -> Path | None:
    """Page through national parking API and keep Daegu rows."""
    rows: list[dict[str, str]] = []
    page = 1
    total = None
    while page <= 200:
        status, ctype, body = _get(
            NATIONAL,
            {
                "serviceKey": key,
                "pageNo": str(page),
                "numOfRows": "1000",
                "type": "json",
            },
            timeout=120,
        )
        if status != 200 or _sniff(body) != "json":
            print(f"national page={page} fail http={status} sniff={_sniff(body)}")
            break
        data = _parse_json(body)
        header = (data.get("response") or {}).get("header") or data.get("header") or {}
        rc = header.get("resultCode") if isinstance(header, dict) else None
        if rc not in ("00", "0", 0, None):
            print(f"national fail resultCode={rc} msg={header}")
            break
        body_obj = (data.get("response") or {}).get("body") or data.get("body") or {}
        if total is None:
            try:
                total = int(body_obj.get("totalCount") or 0)
            except Exception:
                total = 0
        items = body_obj.get("items") or body_obj.get("item") or []
        if isinstance(items, dict):
            # sometimes {"item":[...]}
            if "item" in items:
                items = items["item"]
            else:
                items = [items]
        if not items:
            break
        fetched = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        for it in items:
            if not isinstance(it, dict):
                continue
            addr = str(it.get("rdnmadr") or it.get("lnmadr") or "")
            try:
                lat = float(it["latitude"]) if it.get("latitude") not in (None, "") else None
            except Exception:
                lat = None
            try:
                lng = float(it["longitude"]) if it.get("longitude") not in (None, "") else None
            except Exception:
                lng = None
            if not _in_daegu(lat, lng, addr):
                continue
            row = {k: ("" if v is None else str(v)) for k, v in it.items()}
            row["fetchedAt"] = fetched
            row["parking_source"] = "national_standard"
            rows.append(row)
        print(f"  national page={page} items={len(items)} daegu_acc={len(rows)} total={total}")
        if total and page * 1000 >= total:
            break
        if len(items) < 1000:
            break
        page += 1

    if not rows:
        return None
    EXTRACTED_PARKING.mkdir(parents=True, exist_ok=True)
    path = EXTRACTED_PARKING / f"daegu_parking_info_national_{stamp}.csv"
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # also write latest alias
    latest = EXTRACTED_PARKING / "daegu_parking_info_national_latest.csv"
    latest.write_bytes(path.read_bytes())
    print(f"SAVED {len(rows)} -> {path.relative_to(REPO)}")
    return path


def extract_kotsa_daegu(
    key: str,
    stamp: str,
    *,
    start_page: int = 1,
) -> Path | None:
    """Stream nationwide KOTSA pages and persist Daegu rows only.

    ``start_page`` resumes a retained ``.partial`` output.  Each completed
    page is checkpointed, so an interrupted nationwide scan does not discard
    already filtered Daegu rows.
    """
    page_size = 1000
    page = start_page
    total = None
    daegu_rows = 0
    EXTRACTED_PARKING.mkdir(parents=True, exist_ok=True)
    path = EXTRACTED_PARKING / f"daegu_parking_info_kotsa_{stamp}.csv"
    tmp_path = path.with_suffix(".csv.partial")
    checkpoint_path = tmp_path.with_suffix(".partial.progress.json")
    writer: csv.DictWriter | None = None
    fieldnames: list[str] | None = None
    mode = "w"
    if start_page > 1:
        if not tmp_path.exists():
            raise FileNotFoundError(f"Cannot resume without partial file: {tmp_path}")
        with tmp_path.open(encoding="utf-8-sig", newline="") as prior_file:
            prior_reader = csv.DictReader(prior_file)
            if not prior_reader.fieldnames:
                raise RuntimeError(f"Partial file has no header: {tmp_path}")
            daegu_rows = sum(1 for _ in prior_reader)
            fieldnames = list(prior_reader.fieldnames)
        mode = "a"

    with tmp_path.open(mode, encoding="utf-8-sig", newline="") as out_file:
        if fieldnames is not None:
            writer = csv.DictWriter(
                out_file,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
        while True:
            status = 0
            body = b""
            data: dict | None = None
            last_problem = ""
            for attempt in range(1, 6):
                status, _, body = _get(
                    KOTSA["PrkSttusInfo"],
                    {
                        "serviceKey": key,
                        "pageNo": str(page),
                        "numOfRows": str(page_size),
                        "format": "2",
                    },
                    timeout=90,
                )
                if status != 200:
                    last_problem = f"http={status}"
                elif _sniff(body) != "json":
                    last_problem = f"response={_sniff(body)}"
                else:
                    try:
                        parsed = _parse_json(body)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict) and parsed.get("resultCode") in ("00", "0", 0, None):
                        data = parsed
                        break
                    if isinstance(parsed, dict):
                        last_problem = f"resultCode={parsed.get('resultCode')}"
                    else:
                        last_problem = "invalid JSON"
                if attempt < 5:
                    time.sleep(attempt * 3)
            if data is None:
                raise RuntimeError(
                    f"KOTSA page={page} failed after retries ({last_problem})"
                )
            total = total or data.get("totalCount")
            raw_items = data.get("PrkSttusInfo") or data.get("items") or []
            if isinstance(raw_items, dict):
                raw_items = raw_items.get("item", [raw_items])
            items = [item for item in raw_items if isinstance(item, dict)]
            if not items:
                break

            fetched = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            daegu_page = []
            for item in items:
                if not _is_kotsa_daegu(item):
                    continue
                row = {key: str(value) for key, value in item.items()}
                row["fetchedAt"] = fetched
                row["parking_source"] = "kotsa"
                daegu_page.append(row)
            if daegu_page:
                if writer is None:
                    fieldnames = list(daegu_page[0])
                    writer = csv.DictWriter(out_file, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                writer.writerows(daegu_page)
                daegu_rows += len(daegu_page)

            if page == 1 or page % 50 == 0:
                print(f"  KOTSA page={page} Daegu={daegu_rows} total={total}", flush=True)
            if len(items) < page_size or (total and page * page_size >= int(total)):
                break
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "last_completed_page": page,
                        "next_page": page + 1,
                        "daegu_rows": daegu_rows,
                        "total_rows": total,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            page += 1

    if not daegu_rows:
        tmp_path.unlink(missing_ok=True)
        checkpoint_path.unlink(missing_ok=True)
        return None
    unique_rows = _dedupe_kotsa_csv(tmp_path)
    tmp_path.replace(path)
    checkpoint_path.unlink(missing_ok=True)
    (EXTRACTED_PARKING / "daegu_parking_info_kotsa_latest.csv").write_bytes(path.read_bytes())
    print(f"SAVED {unique_rows} unique Daegu rows -> {path.relative_to(REPO)}")
    return path


def main() -> int:
    load_dotenv(REPO / ".env")
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    pis_k = os.environ.get("DAEGU_PARKING_KEY", "").strip()
    pis_rt = os.environ.get("DAEGU_PARKING_RT_KEY", "").strip()
    kakao = os.environ.get("KAKAO_REST_KEY", "").strip()

    report: dict[str, Any] = {
        "probed_at": datetime.now(KST).isoformat(),
        "keys": {
            "DATA_GO_KR_KEY": _key_meta("DATA_GO_KR_KEY", key),
            "DAEGU_PARKING_KEY": _key_meta("DAEGU_PARKING_KEY", pis_k),
            "DAEGU_PARKING_RT_KEY": _key_meta("DAEGU_PARKING_RT_KEY", pis_rt),
            "KAKAO_REST_KEY": _key_meta("KAKAO_REST_KEY", kakao),
        },
        "probes": [],
        "extracts": {},
        "can_fetch_real_parking": False,
    }

    if not key:
        print("DATA_GO_KR_KEY missing")
        return 1

    print("=== probe KOTSA ===")
    report["probes"].extend(probe_kotsa(key))
    print("=== probe national standard ===")
    report["probes"].append(probe_national(key))
    print("=== probe PIS ===")
    report["probes"].extend(probe_pis(pis_k, pis_rt))

    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    ok_names = {p["name"] for p in report["probes"] if p.get("ok_candidate")}
    print("ok_candidates:", sorted(ok_names))

    # Prefer national (auto-approve) then KOTSA
    nat = next((p for p in report["probes"] if p["name"] == "national_standard"), {})
    if nat.get("resultCode") in ("00", "0", 0) or nat.get("ok_candidate"):
        print("=== extract national Daegu ===")
        path = extract_national_daegu(key, stamp)
        if path:
            report["extracts"]["national"] = str(path.relative_to(REPO)).replace("\\", "/")
            report["can_fetch_real_parking"] = True

    kotsa_ok = any(p.get("ok_candidate") and str(p.get("name", "")).startswith("kotsa_PrkSttus") for p in report["probes"])
    if kotsa_ok:
        print("=== extract KOTSA Daegu ===")
        path = extract_kotsa_daegu(key, stamp)
        if path:
            report["extracts"]["kotsa"] = str(path.relative_to(REPO)).replace("\\", "/")
            report["can_fetch_real_parking"] = True

    OUT_PROBE.mkdir(parents=True, exist_ok=True)
    out_json = OUT_PROBE / "parking_probe_latest.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    stamped = OUT_PROBE / f"parking_probe_{stamp}.json"
    stamped.write_text(out_json.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("keys", "can_fetch_real_parking", "extracts")}, ensure_ascii=False, indent=2))
    print(f"WROTE {out_json}")
    return 0 if report["can_fetch_real_parking"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
