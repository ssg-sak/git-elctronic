"""Build one-click HTML dashboard (no Power BI required) + open it."""
from __future__ import annotations

import json
import webbrowser
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
OUT_DIR = REPO / "포폴용_개인_대시보드_20260809"
DATA = OUT_DIR / "data"
OUT_HTML = OUT_DIR / "대시보드_바로보기.html"
DESK_DIR = Path.home() / "Desktop" / OUT_DIR.name
DESK_HTML = DESK_DIR / "대시보드_바로보기.html"


def _read(name: str) -> pd.DataFrame:
    p = DATA / name
    if not p.is_file():
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8-sig")


def main() -> None:
    meta = _read("dim_meta.csv")
    hour = _read("fact_eda_hour.csv")
    dow = _read("fact_eda_dow.csv")
    fresh = _read("fact_eda_freshness.csv")
    charger = _read("fact_eda_charger_bucket.csv")
    kpi = _read("fact_kpi.csv")
    loo = _read("fact_loo_deltas.csv")
    feats = _read("dim_final_features.csv")
    blocks = _read("fact_reliability_blocks.csv")
    over = _read("fact_overfit_summary.csv")
    fitness = _read("fact_model_fitness.csv")

    as_of = str(meta["as_of"].iloc[0]) if len(meta) and "as_of" in meta.columns else "?"
    pull = str(meta["pull"].iloc[0]) if len(meta) and "pull" in meta.columns else "?"

    def series(df: pd.DataFrame, x: str, y: str):
        if df.empty or x not in df.columns or y not in df.columns:
            return [], []
        d = df.dropna(subset=[x, y]).copy()
        return d[x].astype(str).tolist(), pd.to_numeric(d[y], errors="coerce").fillna(0).tolist()

    # hour
    hx, hy = series(hour, "hour" if "hour" in hour.columns else hour.columns[0], "avail_mean")
    # dow
    dx_col = "dow_ko" if "dow_ko" in dow.columns else ("dow" if "dow" in dow.columns else None)
    dx, dy = series(dow, dx_col, "avail_mean") if dx_col else ([], [])
    # freshness
    fx_col = "age_bucket" if "age_bucket" in fresh.columns else None
    fx, fy = series(fresh, fx_col, "stations") if fx_col else ([], [])
    # charger
    cx_col = "bucket" if "bucket" in charger.columns else None
    cy_col = "d1_avail_mean_observed" if "d1_avail_mean_observed" in charger.columns else "d2_avail_mean"
    cx, cy = series(charger, cx_col, cy_col) if cx_col and cy_col in charger.columns else ([], [])

    # loo
    loo_x, loo_y = [], []
    if not loo.empty:
        feat_col = next((c for c in ("feature", "removed", "col", "name") if c in loo.columns), None)
        metric_col = next(
            (c for c in ("delta_pr_auc", "pr_auc_delta", "delta_prauc", "Δ_pr_auc") if c in loo.columns),
            None,
        )
        if metric_col is None:
            num_cols = [c for c in loo.columns if pd.api.types.is_numeric_dtype(loo[c])]
            metric_col = num_cols[0] if num_cols else None
        if feat_col and metric_col:
            d = loo.dropna(subset=[feat_col, metric_col]).sort_values(metric_col)
            loo_x = d[feat_col].astype(str).tolist()
            loo_y = pd.to_numeric(d[metric_col], errors="coerce").fillna(0).tolist()

    # kpi table
    kpi_rows = []
    if not kpi.empty:
        for _, r in kpi.iterrows():
            kpi_rows.append({k: ("" if pd.isna(v) else str(v)) for k, v in r.items()})

    # features list
    feat_list = []
    if not feats.empty:
        name_col = next((c for c in ("feature", "name", "col", "column") if c in feats.columns), feats.columns[0])
        feat_list = feats[name_col].astype(str).tolist()

    over_txt = ""
    if not over.empty:
        over_txt = over.iloc[0].to_dict()
        over_txt = {k: str(v)[:120] for k, v in over_txt.items()}
    fit_txt = ""
    if not fitness.empty:
        fit_txt = {k: str(v)[:120] for k, v in fitness.iloc[0].to_dict().items()}

    payload = {
        "as_of": as_of,
        "pull": pull,
        "generated": datetime.now(KST).isoformat(timespec="seconds"),
        "hour": {"x": hx, "y": hy},
        "dow": {"x": dx, "y": dy},
        "fresh": {"x": fx, "y": fy},
        "charger": {"x": cx, "y": cy},
        "loo": {"x": loo_x, "y": loo_y},
        "kpi": kpi_rows[:40],
        "features": feat_list[:20],
        "overfit": over_txt,
        "fitness": fit_txt,
        "blocks": blocks.head(20).to_dict(orient="records") if not blocks.empty else [],
    }

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>EV SafeCharge DA① 대시보드 20260809</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg: #0f1419; --card: #1a2332; --text: #e7ecf3; --muted: #9aa7b8;
  --accent: #3d9a6a; --warn: #d4a017; --fail: #c45c26; --line: #2a3545;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
  background: radial-gradient(1200px 600px at 10% -10%, #1c3a2c 0%, transparent 50%),
              radial-gradient(900px 500px at 100% 0%, #243048 0%, transparent 45%),
              var(--bg);
  color: var(--text); padding: 24px;
}}
h1 {{ font-size: 1.6rem; margin: 0 0 8px; letter-spacing: -0.02em; }}
.sub {{ color: var(--muted); margin-bottom: 20px; line-height: 1.5; }}
.grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }}
.card {{
  background: linear-gradient(180deg, #1e2a3a, var(--card));
  border: 1px solid var(--line); border-radius: 14px; padding: 16px 16px 8px;
  grid-column: span 6; min-height: 280px;
}}
.card.wide {{ grid-column: span 12; }}
.card.third {{ grid-column: span 4; min-height: 160px; }}
.card h2 {{ font-size: 0.95rem; margin: 0 0 10px; color: #c5d0de; font-weight: 600; }}
.kpi-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }}
.pill {{
  background: #152030; border: 1px solid var(--line); border-radius: 999px;
  padding: 8px 14px; font-size: 0.85rem;
}}
.pill b {{ color: var(--accent); }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
th, td {{ border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; }}
th {{ color: var(--muted); font-weight: 600; }}
.ok {{ color: var(--accent); }} .warn {{ color: var(--warn); }} .fail {{ color: var(--fail); }}
ul.feats {{ margin: 0; padding-left: 18px; columns: 2; font-size: 0.9rem; }}
a.linkbtn {{
  display: inline-block; margin: 4px 8px 4px 0; padding: 10px 14px; border-radius: 10px;
  background: var(--accent); color: #04140c; text-decoration: none; font-weight: 700; font-size: 0.9rem;
}}
a.linkbtn.sec {{ background: #3a516e; color: #e7ecf3; }}
.note {{ color: var(--muted); font-size: 0.8rem; margin-top: 18px; }}
@media (max-width: 900px) {{
  .card, .card.third {{ grid-column: span 12; }}
  ul.feats {{ columns: 1; }}
}}
</style>
</head>
<body>
<h1>EV SafeCharge · DA① 대시보드</h1>
<div class="sub">
  현재표 as_of <b>{as_of}</b> · pull <b>{pull}</b><br/>
  점수/추천 순위 없음 (②). 브라우저만 있으면 됨.
</div>

<div class="kpi-row">
  <div class="pill">생성 <b>{payload['generated']}</b></div>
  <div class="pill">최종 피처 <b>{len(feat_list)}개</b></div>
  <div class="pill">말하는 이름 <b>현재표 / 시간표</b></div>
</div>

<p>
  <a class="linkbtn" href="https://www.microsoft.com/ko-kr/download/details.aspx?id=58494" target="_blank">Power BI Desktop 받기</a>
  <a class="linkbtn sec" href="https://app.powerbi.com/" target="_blank">Power BI 웹 열기</a>
  <a class="linkbtn sec" href="./00_PowerBI_만들기.md">Power BI 따라하기 (md)</a>
</p>

<div class="grid">
  <div class="card"><h2>E1 · 시간대 가용률 (높을수록 빔)</h2><canvas id="cHour"></canvas></div>
  <div class="card"><h2>E2 · 요일 가용률 (잠정)</h2><canvas id="cDow"></canvas></div>
  <div class="card"><h2>E4 · 신선도 등급별 충전소 수</h2><canvas id="cFresh"></canvas></div>
  <div class="card"><h2>E3 · 충전기 대수 버킷 가용</h2><canvas id="cCharger"></canvas></div>
  <div class="card wide"><h2>HGB · 피처 제거 시 Δ (LOO)</h2><canvas id="cLoo" height="90"></canvas></div>
  <div class="card third"><h2>최종 피처</h2><ul class="feats" id="featList"></ul></div>
  <div class="card third"><h2>적합/과적합 요약</h2><pre id="sumBox" style="white-space:pre-wrap;font-size:0.78rem;color:#c5d0de;margin:0;"></pre></div>
  <div class="card third"><h2>빠른 링크</h2>
    <p style="font-size:0.85rem;color:var(--muted);line-height:1.6;margin:0;">
      1) 이 화면으로 발표 가능<br/>
      2) Power BI 쓰려면 Desktop 설치 후<br/>
      &nbsp;&nbsp;<code>data/</code> CSV 가져오기<br/>
      3) 동대구 ETA = 학습용 고정 origin
    </p>
  </div>
  <div class="card wide"><h2>KPI 표</h2><div style="max-height:320px;overflow:auto;"><table id="kpiTable"></table></div></div>
</div>

<p class="note">포폴 전용(팀 전달 아님) · 포폴용_개인_대시보드_20260809/data</p>

<script>
const D = {json.dumps(payload, ensure_ascii=False)};
const common = {{
  responsive: true,
  plugins: {{ legend: {{ display: false }}, tooltip: {{ mode: 'index' }} }},
  scales: {{
    x: {{ ticks: {{ color: '#9aa7b8' }}, grid: {{ color: '#243044' }} }},
    y: {{ ticks: {{ color: '#9aa7b8' }}, grid: {{ color: '#243044' }} }}
  }}
}};
function line(id, x, y, color) {{
  new Chart(document.getElementById(id), {{
    type: 'line',
    data: {{ labels: x, datasets: [{{ data: y, borderColor: color, backgroundColor: color+'33', fill: true, tension: 0.25, pointRadius: 2 }}] }},
    options: common
  }});
}}
function bar(id, x, y, color) {{
  new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels: x, datasets: [{{ data: y, backgroundColor: color }}] }},
    options: common
  }});
}}
line('cHour', D.hour.x, D.hour.y, '#3d9a6a');
bar('cDow', D.dow.x, D.dow.y, '#5b8fd9');
bar('cFresh', D.fresh.x, D.fresh.y, '#d4a017');
bar('cCharger', D.charger.x, D.charger.y, '#8a6cff');
bar('cLoo', D.loo.x, D.loo.y, '#c45c26');

const ul = document.getElementById('featList');
(D.features||[]).forEach(f => {{ const li=document.createElement('li'); li.textContent=f; ul.appendChild(li); }});

const sum = Object.assign({{}}, D.fitness||{{}}, D.overfit||{{}});
document.getElementById('sumBox').textContent = Object.keys(sum).slice(0,12).map(k => k + ': ' + sum[k]).join('\\n') || '(요약 JSON 없음)';

const tbl = document.getElementById('kpiTable');
if (D.kpi && D.kpi.length) {{
  const keys = Object.keys(D.kpi[0]);
  tbl.innerHTML = '<tr>' + keys.map(k=>'<th>'+k+'</th>').join('') + '</tr>' +
    D.kpi.map(r => '<tr>' + keys.map(k => {{
      const v = r[k]||'';
      const cls = /OK|PASS/i.test(v) ? 'ok' : (/WARN/i.test(v) ? 'warn' : (/FAIL/i.test(v) ? 'fail' : ''));
      return '<td class="'+cls+'">'+v+'</td>';
    }}).join('') + '</tr>').join('');
}} else {{
  tbl.innerHTML = '<tr><td>KPI 표 없음 — fact_kpi.csv 확인</td></tr>';
}}
</script>
</body>
</html>
"""
    OUT_HTML.write_text(html, encoding="utf-8")
    DESK_DIR.mkdir(parents=True, exist_ok=True)
    DESK_HTML.write_text(html, encoding="utf-8")

    # easy launcher
    (OUT_DIR / "★여기를_더블클릭_대시보드.html").write_text(html, encoding="utf-8")

    webbrowser.open(OUT_HTML.resolve().as_uri())

    print(json.dumps({
        "ok": True,
        "html": str(OUT_HTML),
        "desktop": str(DESK_HTML),
        "handoff": False,
    }, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
