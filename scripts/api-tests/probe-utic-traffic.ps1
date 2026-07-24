# UTIC 소통(교통흐름) 프로브 — 키는 .env UTIC_API_KEY
# 돌발(imsOpenData)과 URL이 다를 수 있음. 실패 시 신청 안내 URL을 UTIC_TRAFFIC_URL로 설정 후 재시도.
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
python apps/data-pipeline/processing/probe_utic_traffic.py
exit $LASTEXITCODE
