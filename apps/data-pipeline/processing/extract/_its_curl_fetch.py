"""List + download ITS node-link zip via curl.exe (Windows cert store).

Python requests fails SSL verify against its.go.kr on this machine; curl works.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote


BASE = "https://www.its.go.kr"
PAGE_URL = f"{BASE}/nodelink/nodelinkRef"
LIST_URL = f"{BASE}/opendata/getNodeLinkDataFileList"


def _curl(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    cmd = ["curl.exe", "-sL", *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def fetch_csrf_and_cookie(cookie_jar: Path) -> str:
    cookie_jar.unlink(missing_ok=True)
    html_path = Path(tempfile.gettempdir()) / "its_nodelink_page.html"
    r = _curl(["-c", str(cookie_jar), "-b", str(cookie_jar), "-o", str(html_path), PAGE_URL])
    if r.returncode != 0:
        raise RuntimeError(f"curl page failed: {r.stderr or r.stdout}")
    html = html_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'name="_csrf"\s+content="([^"]+)"', html)
    if not m:
        # cookie fallback
        jar = cookie_jar.read_text(encoding="utf-8", errors="replace")
        xm = re.search(r"XSRF-TOKEN\s+(\S+)", jar)
        if not xm:
            raise RuntimeError("CSRF token not found")
        return xm.group(1)
    return m.group(1)


def list_files(cookie_jar: Path, csrf: str, search_type: int = 90) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=89)
    payload = {
        "body": {
            "data": {
                "searchType": search_type,
                "workingDirectory": "/nodeLink",
                "startDate": start.strftime("%Y%m%d") if search_type == -1 else "",
                "endDate": end.strftime("%Y%m%d") if search_type == -1 else "",
            }
        }
    }
    body_path = Path(tempfile.gettempdir()) / "its_nodelink_list_body.json"
    out_path = Path(tempfile.gettempdir()) / "its_nodelink_list.json"
    body_path.write_text(json.dumps(payload), encoding="utf-8")
    r = _curl(
        [
            "-c",
            str(cookie_jar),
            "-b",
            str(cookie_jar),
            "-X",
            "POST",
            LIST_URL,
            "-H",
            "Content-Type: application/json",
            "-H",
            "Accept: application/json",
            "-H",
            f"X-XSRF-TOKEN: {csrf}",
            "-H",
            f"Origin: {BASE}",
            "-H",
            f"Referer: {PAGE_URL}",
            "--data-binary",
            f"@{body_path}",
            "-o",
            str(out_path),
            "-w",
            "%{http_code}",
        ]
    )
    code = (r.stdout or "").strip()
    raw = out_path.read_text(encoding="utf-8", errors="replace")
    if code and code != "200":
        raise RuntimeError(f"list HTTP {code}: {raw[:300]}")
    j = json.loads(raw)
    if (j.get("header") or {}).get("state") != "OK":
        raise RuntimeError(f"list state not OK: {raw[:500]}")
    return (j.get("body") or {}).get("data", {}).get("fileVOList") or []


def download_file(cookie_jar: Path, csrf: str, file_id: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    candidates = [file_id]
    alt = file_id.replace("[", "(").replace("]", ")")
    if alt != file_id:
        candidates.append(alt)

    last_err = None
    for fid in candidates:
        url = f"{BASE}/common/download?f={quote(fid)}&t=nodeLink"
        # write http code to sidecar
        code_path = Path(tempfile.gettempdir()) / "its_dl_code.txt"
        r = _curl(
            [
                "-c",
                str(cookie_jar),
                "-b",
                str(cookie_jar),
                "-H",
                f"X-XSRF-TOKEN: {csrf}",
                "-H",
                f"Referer: {PAGE_URL}",
                "-o",
                str(dest),
                "-w",
                "%{http_code}",
                url,
            ],
            timeout=900,
        )
        code = (r.stdout or "").strip()
        code_path.write_text(code, encoding="utf-8")
        if r.returncode != 0:
            last_err = RuntimeError(f"curl download rc={r.returncode} {r.stderr}")
            dest.unlink(missing_ok=True)
            continue
        if code not in ("200", "302"):
            last_err = RuntimeError(f"download HTTP {code} for {fid}")
            dest.unlink(missing_ok=True)
            continue
        if not dest.is_file() or dest.stat().st_size < 1_000_000:
            last_err = RuntimeError(
                f"download too small ({dest.stat().st_size if dest.exists() else 0}) for {fid}"
            )
            dest.unlink(missing_ok=True)
            continue
        # zip magic
        with dest.open("rb") as f:
            magic = f.read(4)
        if magic[:2] != b"PK":
            last_err = RuntimeError(f"not a zip for {fid}: magic={magic!r}")
            dest.unlink(missing_ok=True)
            continue
        return dest
    assert last_err is not None
    raise last_err
