"""전체 파이프라인 진입점.

수집 -> 히스토리 저장 -> 신호(A/B) 계산 -> 뉴스 요약(C) -> 대시보드(D) 생성 -> 이메일 발송

로컬 테스트: (.env를 만든 뒤) 아래처럼 실행
    python -m src.main

GitHub Actions에서는 .github/workflows/daily_report.yml 이 매일 자동으로 호출한다.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
from dotenv import load_dotenv
from pykrx import stock

load_dotenv()  # 로컬 테스트용. GitHub Actions에서는 .env가 없으므로 조용히 무시된다.

from src.build_report import (
    build_dashboard_html,
    build_excel_attachment,
    build_html_body,
)
from src.collect import INVESTOR_TYPES, collect_all
from src.history import load_recent_snapshots, save_daily_snapshot
from src.news import search_news, summarize_stock_news
from src.send_mail import send_report
from src.signals import (
    DEFAULT_LOOKBACK,
    DEFAULT_STREAK_THRESHOLD,
    LONG_WINDOW,
    SHORT_WINDOW,
    foreign_streak_signals,
    trend_reversal_signals,
)

MAX_NEWS_TARGETS = 10  # 뉴스 요약 API 호출 비용을 통제하기 위한 상한
HISTORY_WINDOW = max(DEFAULT_LOOKBACK, LONG_WINDOW)


def _compute_signals(target_date: str, df: pd.DataFrame):
    save_daily_snapshot(target_date, df)
    history = load_recent_snapshots(n_days=HISTORY_WINDOW, upto_date=target_date)

    signals_a = pd.DataFrame()
    signals_b = pd.DataFrame()

    if len(history) >= 2:
        dates = sorted(history.keys())[-DEFAULT_LOOKBACK:]
        try:
            index_close = stock.get_index_ohlcv_by_date(dates[0], dates[-1], "1001")["종가"]
            index_close.index = index_close.index.strftime("%Y%m%d")
            signals_a = foreign_streak_signals(history, index_close)
        except Exception as exc:  # noqa: BLE001
            print(f"Section A 계산 실패: {exc}", file=sys.stderr)

    if len(history) >= SHORT_WINDOW + 1:
        signals_b = trend_reversal_signals(history, list(INVESTOR_TYPES.keys()))

    if len(history) < HISTORY_WINDOW:
        print(
            f"히스토리 {len(history)}/{HISTORY_WINDOW}일치만 누적됨. "
            "Section A/B는 데이터가 쌓이는 대로 점점 채워집니다."
        )

    return signals_a, signals_b


def _collect_news(signals_a: pd.DataFrame, signals_b: pd.DataFrame) -> dict[str, dict]:
    targets: list[tuple[str, str, str]] = []  # (종목코드, 종목명, 사유)
    for _, r in signals_a.iterrows():
        targets.append((r["종목코드"], r["종목명"], "최근 외국인 연속 순매수"))
    for _, r in signals_b.iterrows():
        targets.append((r["종목코드"], r["종목명"], f"{r['투자자유형']} 매매동향 전환"))

    seen: set[str] = set()
    news_comments: dict[str, dict] = {}
    for code, name, reason in targets:
        if code in seen or len(seen) >= MAX_NEWS_TARGETS:
            continue
        seen.add(code)
        try:
            articles = search_news(name)
            comment = summarize_stock_news(name, reason, articles)
            news_comments[code] = {"종목명": name, "comment": comment, "articles": articles}
        except Exception as exc:  # noqa: BLE001
            print(f"뉴스 요약 실패 ({name}): {exc}", file=sys.stderr)

    return news_comments


def main() -> int:
    try:
        target_date, df = collect_all()
    except Exception as exc:  # noqa: BLE001 - 파이프라인 최상위이므로 넓게 잡아 로그만 남김
        print(f"데이터 수집 실패: {exc}", file=sys.stderr)
        return 1

    signals_a, signals_b = _compute_signals(target_date, df)
    news_comments = _collect_news(signals_a, signals_b)
    dashboard_path = build_dashboard_html(target_date, df)

    dashboard_url = os.getenv("DASHBOARD_BASE_URL")
    if dashboard_url:
        dashboard_url = dashboard_url.rstrip("/") + "/"

    html_body = build_html_body(
        target_date,
        df,
        signals_a,
        signals_b,
        news_comments,
        lookback=DEFAULT_LOOKBACK,
        threshold=DEFAULT_STREAK_THRESHOLD,
        short_window=SHORT_WINDOW,
        long_window=LONG_WINDOW,
        dashboard_url=dashboard_url,
    )
    excel_bytes = build_excel_attachment(df)

    subject = f"[코스피 매매동향] {target_date}"
    try:
        send_report(subject, html_body, excel_bytes, f"kospi_{target_date}.xlsx")
    except Exception as exc:  # noqa: BLE001
        print(f"이메일 발송 실패: {exc}", file=sys.stderr)
        return 1

    print(
        f"리포트 발송 완료: {target_date}, {len(df)}종목, "
        f"A:{len(signals_a)}건 B:{len(signals_b)}건 뉴스:{len(news_comments)}건, "
        f"대시보드: {dashboard_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
