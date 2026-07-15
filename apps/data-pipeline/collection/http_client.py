"""공공 API 호출 공통 래퍼: 재시도(백오프), 원본 응답 아카이빙."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import requests

import config
from logging_conf import get_logger

logger = get_logger(__name__)


class ApiCallError(RuntimeError):
    """재시도 후에도 실패한 API 호출."""


def request_with_retry(
    method: str,
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    json_body: Optional[dict[str, Any]] = None,
    max_retries: int = config.MAX_RETRIES,
    timeout: int = config.REQUEST_TIMEOUT_SECONDS,
) -> requests.Response:
    """502/504·타임아웃·연결 오류 시 지수형이 아닌 고정 대기 후 재시도한다.

    403은 재시도해도 즉시 해결되지 않는 경우가 많아(신규 키 동기화 지연) 경고만 남기고 그대로 진행한다.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 2):
        try:
            resp = requests.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json_body,
                timeout=timeout,
            )
            if resp.status_code == 403:
                logger.warning("403 Forbidden — 신규 키 동기화 대기(최대 1시간) 가능성: %s", url)
            if resp.status_code in (502, 504):
                raise ApiCallError(f"{resp.status_code} 게이트웨이 오류")
            resp.raise_for_status()
            return resp
        except (requests.RequestException, ApiCallError) as exc:
            last_exc = exc
            if attempt <= max_retries:
                logger.warning(
                    "호출 실패(%s번째 시도), %s초 후 재시도: %s", attempt, config.RETRY_BACKOFF_SECONDS, exc
                )
                time.sleep(config.RETRY_BACKOFF_SECONDS)
            else:
                logger.error("재시도 소진, 호출 최종 실패: %s", exc)
    assert last_exc is not None
    raise ApiCallError(str(last_exc))


def archive_raw(api_name: str, content: Union[bytes, str], extension: str) -> Path:
    """원본 응답을 가공 없이 raw/ 아래에 그대로 보존한다 (git 미추적)."""
    subdir = config.RAW_DIR / api_name
    subdir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%dT%H%M%S%f')}.{extension}"
    path = subdir / filename
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path
