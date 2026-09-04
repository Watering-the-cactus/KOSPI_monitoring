"""수집/신호 데이터로 이메일 본문(HTML), 첨부파일(xlsx), 대시보드(HTML)를 만든다.

이메일 본문 구성:
    1. 탑픽 (외국인 연속 순매수로 거른 종목 + 수익률/거래량/타 투자자 매매동향 보조지표)
    2. 탑픽별 뉴스 요약/관전 포인트 카드
    3. 추세 전환 관찰 종목 (보조, 축약형)
    4. 상세 대시보드 링크

투자자 유형별 전체 순매수/순매도 상위 종목은 이메일 본문이 아니라
xlsx 첨부의 별도 시트로만 정리한다 (build_excel_attachment 참고).
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

INVESTOR_LABELS = ["개인", "기관", "외국인", "기타법인"]
TOP_N = 20
TOP_PICKS_LIMIT = 20

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


# ---------------------------------------------------------------------------
# 공통 포맷 헬퍼
# ---------------------------------------------------------------------------


def _format_money(v) -> str:
    return f"{v:,.0f}" if pd.notna(v) else "-"


def _format_pct(v) -> str:
    return f"{v * 100:.2f}%" if pd.notna(v) else "-"


def _signed_cell(v, formatter=_format_money) -> str:
    """양수는 초록, 음수는 빨강으로 칠한 <span>을 반환한다."""
    if pd.isna(v):
        return "<span class='num'>-</span>"
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    sign = "+" if v > 0 else ""
    return f"<span class='num {cls}'>{sign}{formatter(v)}</span>"


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_EMAIL_CSS = """
body { margin:0; padding:0; background:#f2f4f7;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       color:#1f2430; }
.container { max-width:820px; margin:0 auto; padding:20px 14px; }
.header { background:#1e3a5f; background:linear-gradient(135deg,#1e3a5f,#2c6e9e);
          color:#ffffff; padding:22px 26px; border-radius:10px 10px 0 0; }
.header h1 { margin:0; font-size:19px; font-weight:700; }
.header p { margin:6px 0 0; font-size:12.5px; opacity:.85; }
.section { background:#ffffff; padding:22px 26px; border:1px solid #e3e6ec; border-top:none; }
.section:last-of-type { border-radius:0 0 10px 10px; }
.section h2 { font-size:15.5px; margin:0 0 4px; color:#1e3a5f; }
.section .desc { font-size:12px; color:#6b7280; margin:0 0 14px; line-height:1.5; }
table { width:100%; border-collapse:collapse; font-size:12.5px; }
th { background:#f4f6fa; color:#4b5563; text-align:right; padding:8px 10px;
     font-weight:600; border-bottom:2px solid #e3e6ec; white-space:nowrap; }
th:first-child, th:nth-child(2) { text-align:left; }
td { padding:8px 10px; border-bottom:1px solid #eef0f4; text-align:right; white-space:nowrap; }
td:first-child, td:nth-child(2) { text-align:left; white-space:normal; }
tr:nth-child(even) td { background:#fafbfd; }
.num { font-variant-numeric:tabular-nums; }
.pos { color:#0a7a3d; font-weight:600; }
.neg { color:#c0392b; font-weight:600; }
.rank { display:inline-block; min-width:20px; text-align:center; font-weight:700;
        color:#2c6e9e; }
.news-card { border:1px solid #e3e6ec; border-radius:8px; padding:14px 16px;
             margin-bottom:10px; background:#fbfcfe; }
.news-card h3 { margin:0 0 6px; font-size:13.5px; color:#1e3a5f; }
.news-card p { margin:0 0 8px; font-size:12.5px; line-height:1.55; color:#374151; }
.news-card ul { margin:0; padding-left:16px; font-size:11.5px; }
.news-card a { color:#2c6e9e; text-decoration:none; }
.cta { display:inline-block; margin-top:4px; padding:9px 18px; background:#1e3a5f;
       color:#ffffff !important; border-radius:6px; text-decoration:none; font-size:13px;
       font-weight:600; }
.footer { text-align:center; font-size:11px; color:#9aa0ab; padding:16px 8px; }
.table-wrap { overflow-x:auto; }
"""


# ---------------------------------------------------------------------------
# 1. 탑픽
# ---------------------------------------------------------------------------


def top_picks_table_html(top_picks: pd.DataFrame, lookback: int, threshold: int) -> str:
    header = (
        f"<h2>🎯 오늘의 탑픽</h2>"
        f"<p class='desc'>최근 {lookback}거래일 중 {threshold}일 이상 외국인이 순매수한 "
        f"종목 중 누적 순매수대금 상위 {TOP_PICKS_LIMIT}개입니다. 수익률/거래량/타 투자자 "
        f"매매동향은 참고용 보조지표이며 매수 추천이 아닙니다.</p>"
    )
    if top_picks.empty:
        return header + "<p>조건을 만족하는 종목이 없습니다.</p>"

    cum_col = [c for c in top_picks.columns if c.endswith("일_누적순매수대금")][0]

    rows = []
    for i, (_, r) in enumerate(top_picks.iterrows(), start=1):
        rows.append(
            "<tr>"
            f"<td><span class='rank'>{i}</span></td>"
            f"<td><b>{r['종목명']}</b><br><span style='color:#9aa0ab;font-size:11px'>{r['종목코드']}</span></td>"
            f"<td class='num'>{r['순매수일수']}/{r['lookback일수']}</td>"
            f"<td class='num'>{_signed_cell(r[cum_col])}</td>"
            f"<td class='num'>{_signed_cell(r['구간수익률'], _format_pct)}</td>"
            f"<td class='num'>{_signed_cell(r['지수대비_초과수익률'], _format_pct)}</td>"
            f"<td class='num'>{_signed_cell(r['거래대금_변화율'], _format_pct)}</td>"
            f"<td class='num'>{_signed_cell(r.get('개인_누적순매수대금'))}</td>"
            f"<td class='num'>{_signed_cell(r.get('기관_누적순매수대금'))}</td>"
            f"<td class='num'>{_signed_cell(r.get('기타법인_누적순매수대금'))}</td>"
            "</tr>"
        )

    table = (
        "<div class='table-wrap'><table>"
        "<tr><th>#</th><th>종목</th><th>외인매수일</th><th>외인누적순매수</th>"
        "<th>구간수익률</th><th>지수대비초과</th><th>거래대금변화</th>"
        "<th>개인누적</th><th>기관누적</th><th>기타법인누적</th></tr>"
        f"{''.join(rows)}</table></div>"
    )
    return header + table


# ---------------------------------------------------------------------------
# 2. 탑픽별 뉴스
# ---------------------------------------------------------------------------


def news_cards_html(top_picks: pd.DataFrame, news_comments: dict[str, dict]) -> str:
    header = "<h2>📰 탑픽 뉴스 &amp; 관전 포인트</h2>"
    if top_picks.empty or not news_comments:
        return header + "<p>요약 대상 종목이 없습니다.</p>"

    cards = []
    for _, r in top_picks.iterrows():
        code = r["종목코드"]
        info = news_comments.get(code)
        if not info:
            continue
        links = "".join(
            f"<li><a href='{a['link']}'>{a['title']}</a></li>" for a in info.get("articles", [])
        )
        cards.append(
            f"<div class='news-card'><h3>{r['종목명']} ({code})</h3>"
            f"<p>{info.get('comment', '')}</p>"
            f"<ul>{links}</ul></div>"
        )

    if not cards:
        return header + "<p>요약 대상 종목이 없습니다.</p>"
    return header + "".join(cards)


# ---------------------------------------------------------------------------
# 전체 이메일 본문
# ---------------------------------------------------------------------------


def build_html_body(
    target_date: str,
    df: pd.DataFrame,
    signals_a: pd.DataFrame,
    news_comments: dict[str, dict],
    lookback: int,
    threshold: int,
    dashboard_url: str | None = None,
) -> str:
    top_picks = (
        signals_a.head(TOP_PICKS_LIMIT) if not signals_a.empty else signals_a
    )

    dashboard_block = ""
    if dashboard_url:
        dashboard_block = (
            "<div class='section'><h2>📊 상세 대시보드</h2>"
            "<p class='desc'>코스피 시가총액 상위 종목 정렬/검색 가능한 표를 웹에서 볼 수 있습니다.</p>"
            f"<a class='cta' href='{dashboard_url}'>대시보드 열기 →</a></div>"
        )

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>{_EMAIL_CSS}</style></head>
<body><div class="container">
  <div class="header">
    <h1>코스피 투자자별 매매동향 &middot; {target_date}</h1>
    <p>시가총액 상위 {len(df)}개 중 탑픽 {len(top_picks)}개 · 전체 데이터는 첨부 엑셀 참고</p>
  </div>
  <div class="section">{top_picks_table_html(top_picks, lookback, threshold)}</div>
  <div class="section">{news_cards_html(top_picks, news_comments)}</div>
  {dashboard_block}
  <div class="footer">이 리포트는 자동 생성되었으며 투자 판단의 참고 자료일 뿐 매수/매도 추천이 아닙니다.</div>
</div></body></html>"""


# ---------------------------------------------------------------------------
# xlsx 첨부: 전종목 원본 + 투자자 유형별 상위 종목 + 탑픽 전체 리스트
# ---------------------------------------------------------------------------


def _top_n_df(df: pd.DataFrame, label: str, ascending: bool, n: int = TOP_N) -> pd.DataFrame:
    col = f"{label}_순매수거래대금"
    cols = ["종목명", "종목코드", col, "등락률"]
    return df.sort_values(col, ascending=ascending).head(n)[cols]


def build_excel_attachment(
    df: pd.DataFrame,
    signals_a: pd.DataFrame | None = None,
    signals_b: pd.DataFrame | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="전종목")

        if signals_a is not None and not signals_a.empty:
            signals_a.to_excel(writer, index=False, sheet_name="외국인연속매수_전체")

        if signals_b is not None and not signals_b.empty:
            signals_b.to_excel(writer, index=False, sheet_name="추세전환관찰")

        for label in INVESTOR_LABELS:
            buy = _top_n_df(df, label, ascending=False)
            sell = _top_n_df(df, label, ascending=True)
            sheet = f"{label}_TOP"
            buy.to_excel(writer, index=False, sheet_name=sheet, startrow=1)
            gap = len(buy) + 3
            sell.to_excel(writer, index=False, sheet_name=sheet, startrow=gap + 1)

            ws = writer.sheets[sheet]
            ws.cell(row=1, column=1, value=f"{label} 순매수 상위 {TOP_N}")
            ws.cell(row=gap, column=1, value=f"{label} 순매도 상위 {TOP_N}")

    return buffer.getvalue()


# ---------------------------------------------------------------------------
# 대시보드 (GitHub Pages로 게시)
# ---------------------------------------------------------------------------

_DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>코스피 매매동향 대시보드 ({date})</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 24px; }}
  input {{ padding: 6px 10px; margin-bottom: 12px; width: 240px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ cursor: pointer; background: #f0f0f0; position: sticky; top: 0; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #1e1e1e; color: #eee; }}
    th {{ background: #333; }}
    th, td {{ border-color: #444; }}
  }}
</style>
</head>
<body>
<h2>코스피 전종목 투자자별 매매동향 ({date})</h2>
<input id="filter" placeholder="종목명/코드 검색">
<table id="tbl">
<thead><tr>{header_cells}</tr></thead>
<tbody>{body_rows}</tbody>
</table>
<script>
const table = document.getElementById('tbl');
const filterInput = document.getElementById('filter');
filterInput.addEventListener('input', () => {{
  const q = filterInput.value.toLowerCase();
  for (const row of table.tBodies[0].rows) {{
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  }}
}});
table.tHead.addEventListener('click', (e) => {{
  const th = e.target.closest('th');
  if (!th) return;
  const idx = th.cellIndex;
  const asc = th.dataset.asc !== 'true';
  th.dataset.asc = asc;
  const rows = [...table.tBodies[0].rows];
  rows.sort((a, b) => {{
    const av = a.cells[idx].textContent.replace(/,/g, '');
    const bv = b.cells[idx].textContent.replace(/,/g, '');
    const an = parseFloat(av), bn = parseFloat(bv);
    const cmp = !isNaN(an) && !isNaN(bn) ? an - bn : av.localeCompare(bv);
    return asc ? cmp : -cmp;
  }});
  rows.forEach(r => table.tBodies[0].appendChild(r));
}});
</script>
</body>
</html>
"""


def build_dashboard_html(target_date: str, df: pd.DataFrame) -> Path:
    columns = list(df.columns)
    header_cells = "".join(f"<th>{c}</th>" for c in columns)
    body_rows = "".join(
        "<tr>" + "".join(f"<td>{row[c]}</td>" for c in columns) + "</tr>"
        for _, row in df.iterrows()
    )

    html = _DASHBOARD_TEMPLATE.format(
        date=target_date, header_cells=header_cells, body_rows=body_rows
    )

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCS_DIR / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
