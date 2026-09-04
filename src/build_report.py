"""수집/신호 데이터로 이메일 본문(HTML), 첨부파일(xlsx), 대시보드(HTML)를 만든다.

이메일 본문 구성 순서:
    A. 외국인 연속 순매수 종목
    B. 추세 전환 관찰 종목
    C. 위 종목들에 대한 뉴스 요약/전망 코멘트
    D. 상세 대시보드 링크
    E. (부록) 투자자 유형별 순매수/순매도 상위 20종목
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

INVESTOR_LABELS = ["개인", "기관", "외국인", "기타법인"]
TOP_N = 20

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def _format_money(v) -> str:
    return f"{v:,.0f}" if pd.notna(v) else "-"


def _format_pct(v) -> str:
    return f"{v * 100:.2f}%" if pd.notna(v) else "-"


# ---------------------------------------------------------------------------
# A. 외국인 연속 순매수
# ---------------------------------------------------------------------------


def section_a_html(signals_a: pd.DataFrame, lookback: int, threshold: int) -> str:
    header = (
        f"<h3>A. 외국인 연속 순매수 종목 (최근 {lookback}거래일 중 {threshold}일 이상)</h3>"
    )
    if signals_a.empty:
        return header + "<p>조건을 만족하는 종목이 없습니다.</p>"

    cum_col = [c for c in signals_a.columns if c.endswith("누적순매수대금")][0]
    rows = "".join(
        "<tr>"
        f"<td>{r['종목명']}</td><td>{r['종목코드']}</td>"
        f"<td style='text-align:right'>{r['순매수일수']}/{r['lookback일수']}</td>"
        f"<td style='text-align:right'>{_format_money(r[cum_col])}</td>"
        f"<td style='text-align:right'>{_format_pct(r['거래대금_변화율'])}</td>"
        f"<td style='text-align:right'>{_format_pct(r['구간수익률'])}</td>"
        f"<td style='text-align:right'>{_format_pct(r['지수대비_초과수익률'])}</td>"
        "</tr>"
        for _, r in signals_a.iterrows()
    )
    table = (
        "<table border='1' cellspacing='0' cellpadding='4' "
        "style='border-collapse:collapse;font-size:13px;margin-bottom:8px'>"
        "<tr style='background:#f0f0f0'>"
        "<th>종목명</th><th>종목코드</th><th>순매수일수</th><th>누적순매수대금</th>"
        "<th>거래대금 변화율<br>(최근3일 vs 이전)</th><th>구간수익률</th><th>지수대비 초과수익률</th>"
        "</tr>"
        f"{rows}</table>"
    )
    note = (
        "<p style='font-size:12px;color:#666'>거래대금 변화율/지수대비 초과수익률은 "
        "매수 효과를 예측하는 지표가 아니라, 해당 구간의 거래량/가격 움직임을 "
        "참고하기 위한 보조지표입니다.</p>"
    )
    return header + table + note


# ---------------------------------------------------------------------------
# B. 추세 전환 관찰 종목
# ---------------------------------------------------------------------------


def section_b_html(signals_b: pd.DataFrame, short_window: int, long_window: int) -> str:
    header = (
        f"<h3>B. 추세 전환 관찰 종목 (최근 {short_window}일 평균 부호가 "
        f"이전 {long_window - short_window}일 평균과 반대)</h3>"
    )
    if signals_b.empty:
        return header + "<p>조건을 만족하는 종목이 없습니다.</p>"

    recent_col = [c for c in signals_b.columns if c.startswith("최근")][0]
    prior_col = [c for c in signals_b.columns if c.startswith("이전")][0]
    rows = "".join(
        "<tr>"
        f"<td>{r['종목명']}</td><td>{r['종목코드']}</td><td>{r['투자자유형']}</td>"
        f"<td style='text-align:right'>{_format_money(r[recent_col])}</td>"
        f"<td style='text-align:right'>{_format_money(r[prior_col])}</td>"
        "</tr>"
        for _, r in signals_b.iterrows()
    )
    table = (
        "<table border='1' cellspacing='0' cellpadding='4' "
        "style='border-collapse:collapse;font-size:13px'>"
        "<tr style='background:#f0f0f0'>"
        "<th>종목명</th><th>종목코드</th><th>투자자유형</th>"
        f"<th>최근{short_window}일 평균</th><th>이전 평균</th>"
        "</tr>"
        f"{rows}</table>"
    )
    return header + table


# ---------------------------------------------------------------------------
# C. 뉴스 요약/전망 코멘트
# ---------------------------------------------------------------------------


def section_c_html(news_comments: dict[str, dict]) -> str:
    header = "<h3>C. 종목별 뉴스 요약 및 관전 포인트</h3>"
    if not news_comments:
        return header + "<p>요약 대상 종목이 없습니다.</p>"

    blocks = []
    for code, info in news_comments.items():
        name = info.get("종목명", code)
        comment = info.get("comment", "")
        links = "".join(
            f"<li><a href='{a['link']}'>{a['title']}</a></li>" for a in info.get("articles", [])
        )
        blocks.append(
            f"<p><b>{name} ({code})</b><br>{comment}</p>"
            f"<ul style='font-size:12px'>{links}</ul>"
        )
    return header + "".join(blocks)


# ---------------------------------------------------------------------------
# E. (부록) 투자자 유형별 상위 종목
# ---------------------------------------------------------------------------


def _top_table_html(df: pd.DataFrame, label: str, ascending: bool) -> str:
    col = f"{label}_순매수거래대금"
    top = df.sort_values(col, ascending=ascending).head(TOP_N)

    rows = "".join(
        "<tr>"
        f"<td>{r['종목명']}</td>"
        f"<td>{r['종목코드']}</td>"
        f"<td style='text-align:right'>{_format_money(r[col])}</td>"
        f"<td style='text-align:right'>{r['등락률']:.2f}%</td>"
        "</tr>"
        for _, r in top.iterrows()
    )
    return (
        "<table border='1' cellspacing='0' cellpadding='4' "
        "style='border-collapse:collapse;font-size:13px;margin-bottom:16px'>"
        "<tr style='background:#f0f0f0'>"
        "<th>종목명</th><th>종목코드</th><th>순매수대금(원)</th><th>등락률</th>"
        "</tr>"
        f"{rows}</table>"
    )


def section_e_html(df: pd.DataFrame) -> str:
    sections = []
    for label in INVESTOR_LABELS:
        buy_table = _top_table_html(df, label, ascending=False)
        sell_table = _top_table_html(df, label, ascending=True)
        sections.append(
            f"<h4>{label} 순매수 상위 {TOP_N}</h4>{buy_table}"
            f"<h4>{label} 순매도 상위 {TOP_N}</h4>{sell_table}"
        )
    return "<h3>E. (부록) 투자자 유형별 순매수/순매도 상위 종목</h3>" + "".join(sections)


# ---------------------------------------------------------------------------
# 전체 이메일 본문
# ---------------------------------------------------------------------------


def build_html_body(
    target_date: str,
    df: pd.DataFrame,
    signals_a: pd.DataFrame,
    signals_b: pd.DataFrame,
    news_comments: dict[str, dict],
    lookback: int,
    threshold: int,
    short_window: int,
    long_window: int,
    dashboard_url: str | None = None,
) -> str:
    parts = [
        f"<h2>코스피 투자자별 매매동향 ({target_date})</h2>",
        section_a_html(signals_a, lookback, threshold),
        section_b_html(signals_b, short_window, long_window),
        section_c_html(news_comments),
    ]
    if dashboard_url:
        parts.append(
            f"<h3>D. 상세 대시보드</h3><p><a href='{dashboard_url}'>전종목 대시보드 바로가기</a></p>"
        )
    parts.append(f"<p>전종목 {len(df)}개 원본 데이터는 첨부된 엑셀 파일을 참고하세요.</p>")
    parts.append(section_e_html(df))
    return "".join(parts)


def build_excel_attachment(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="전종목")
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
