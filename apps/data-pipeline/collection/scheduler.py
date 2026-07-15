"""수집 스케줄러: getChargerInfo(매일 03:00) · getChargerStatus(3분 간격) · 카카오 로컬(매일 03:30).

실행: python scheduler.py
시작 시 getChargerInfo를 1회 즉시 실행해 충전소 목록을 부트스트랩한다.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import db
import ev_charger_info
import ev_charger_status
import kakao_local
from logging_conf import get_logger

logger = get_logger(__name__)


def _run_safely(name: str, func) -> None:
    try:
        func()
    except Exception:
        logger.exception("%s 실행 중 오류 발생", name)


def job_charger_info() -> None:
    _run_safely("getChargerInfo", ev_charger_info.collect)


def job_charger_status() -> None:
    _run_safely("getChargerStatus", ev_charger_status.collect)


def job_kakao_local() -> None:
    _run_safely("카카오 로컬", kakao_local.collect)


def main() -> None:
    db.init_db()
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    logger.info("초기 부트스트랩: getChargerInfo 최초 1회 실행")
    job_charger_info()
    job_charger_status()

    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(job_charger_info, CronTrigger(hour=3, minute=0), id="charger_info")
    scheduler.add_job(job_charger_status, IntervalTrigger(minutes=3), id="charger_status")
    scheduler.add_job(job_kakao_local, CronTrigger(hour=3, minute=30), id="kakao_local")

    logger.info("수집 스케줄러 시작: getChargerInfo 매일 03:00 / getChargerStatus 3분 간격 / 카카오 로컬 매일 03:30")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 종료")


if __name__ == "__main__":
    main()
