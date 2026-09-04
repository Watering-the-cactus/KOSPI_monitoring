"""과거 데이터를 data/ 에 한 번에 채워 넣거나(백필), 외국인 연속매수 임계값(N)별
분포를 탐색하는 스크립트.

daily 파이프라인(src/collect.py)은 투자자 유형당 전종목을 한 번에 조회해서
호출 4번으로 끝나지만, 이 스크립트는 반대로 "티커 하나당 날짜 범위 조회"를 쓰기
때문에 종목 수만큼 호출이 필요하다(코스피 전종목 기준 800회 이상, 완료까지
몇 분 정도 소요). 그래서 매일 자동으로 돌리는 게 아니라, 파이프라인을 처음 시작할 때
히스토리를 미리 채워두거나(그래야 Section A/B가 첫날부터 동작한다), 임계값을
가끔 다시 점검할 때 로컬에서 수동으로 실행하는 용도다.

사용 예:
    python -m scripts.backfill_history --days 20                    # data/ 시딩
    python -m scripts.backfill_history --days 60 --explore-thresholds  # N별 분포만 확인, 저장 안 함
"""
from __future__ import annotations

import argparse
import time

import pandas as pd
from dotenv import load_dotenv
from pykrx import stock

from src.collect import check_krx_credentials
from src.history import save_daily_snapshot

load_dotenv()  # 로컬 실행용. GitHub Actions에서는 .env가 없으므로 조용히 무시된다.

INVESTOR_COLUMN_MAP = {
    "개인": "개인",
    "기관": "기관합계",
    "외국인": "외국인합계",
    "기타법인": "기타법인",
}


def _trading_dates(days: int) -> list[str]:
    today = stock.get_nearest_business_day_in_a_week(prev=True)
    start_guess = (pd.Timestamp(today) - pd.Timedelta(days=days * 2 + 10)).strftime("%Y%m%d")
    trading_days = stock.get_previous_business_days(fromdate=start_guess, todate=today)
    dates = [pd.Timestamp(d).strftime("%Y%m%d") for d in trading_days]
    return dates[-days:]


def collect_history(days: int, market: str = "KOSPI") -> dict[str, pd.DataFrame]:
    """지난 days거래일치 스냅샷을 {날짜: DataFrame} 형태로 만들어 반환한다."""
    check_krx_credentials()
    dates = _trading_dates(days)
    tickers = stock.get_market_ticker_list(dates[-1], market=market)
    print(f"대상 기간: {dates[0]} ~ {dates[-1]} ({len(dates)}거래일), 종목 수: {len(tickers)}")

    ohlcv_by_date = {d: stock.get_market_ohlcv_by_ticker(d, market=market) for d in dates}

    rows_by_date: dict[str, list[dict]] = {d: [] for d in dates}
    for i, ticker in enumerate(tickers, start=1):
        try:
            trades = stock.get_market_trading_value_by_date(dates[0], dates[-1], ticker)
        except Exception as exc:  # noqa: BLE001
            print(f"  {ticker} 조회 실패: {exc}")
            continue

        # 거래정지/데이터 공백 등으로 빈 응답이 오면(예외 없이 빈 DataFrame만 옴)
        # index가 RangeIndex라 strftime이 없어 그대로는 죽는다. 건너뛴다.
        if trades is None or trades.empty:
            continue

        name = stock.get_market_ticker_name(ticker)
        trades.index = trades.index.strftime("%Y%m%d")

        for d in dates:
            if d not in trades.index:
                continue
            trade_row = trades.loc[d]
            price_table = ohlcv_by_date.get(d)
            has_price = price_table is not None and ticker in price_table.index
            price_row = price_table.loc[ticker] if has_price else None

            rows_by_date[d].append(
                {
                    "종목코드": ticker,
                    "종목명": name,
                    **{
                        f"{label}_순매수거래대금": trade_row.get(col, 0)
                        for label, col in INVESTOR_COLUMN_MAP.items()
                    },
                    "종가": price_row["종가"] if price_row is not None else None,
                    "등락률": price_row["등락률"] if price_row is not None else None,
                    "거래대금": price_row["거래대금"] if price_row is not None else None,
                }
            )

        time.sleep(0.3)  # 연속 호출 간 짧은 대기
        if i % 50 == 0:
            print(f"  {i}/{len(tickers)} 종목 수집...")

    return {d: pd.DataFrame(rows) for d, rows in rows_by_date.items()}


def explore_thresholds(
    history: dict[str, pd.DataFrame], candidates: list[int], lookback: int = 10
) -> None:
    """N별로, 쌓인 기간 전체에 걸쳐 10일짜리 창을 하루씩 밀어가며(rolling)
    "그날 몇 종목이 조건을 만족했는지"를 계산하고 그 분포(평균/중앙값/0건인 날
    비율)를 출력한다. 창 하나만 보고 판단하는 것보다 훨씬 안정적인 근거가 된다.
    """
    from src.signals import foreign_streak_signals

    dates = sorted(history.keys())
    if len(dates) < lookback + 1:
        print(f"히스토리가 {len(dates)}일치뿐이라 롤링 비교를 하기엔 부족합니다.")
        return

    index_close = stock.get_index_ohlcv_by_date(dates[0], dates[-1], "1001")["종가"]
    index_close.index = index_close.index.strftime("%Y%m%d")

    windows = range(lookback, len(dates) + 1)
    print(f"\n평가 대상: {len(dates)}거래일 데이터, {len(list(windows))}개 롤링 창(각 {lookback}일)")

    for n in candidates:
        daily_counts = []
        for end_idx in windows:
            window_dates = dates[end_idx - lookback : end_idx]
            window_history = {d: history[d] for d in window_dates}
            result = foreign_streak_signals(
                window_history, index_close, lookback=lookback, threshold=n
            )
            daily_counts.append(len(result))

        s = pd.Series(daily_counts)
        print(f"\n--- threshold={n} ---")
        print(f"0건인 날: {(s == 0).sum()}/{len(s)}일")
        print(s.describe())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 개수만 확인")
    parser.add_argument(
        "--explore-thresholds",
        action="store_true",
        help="6/7/8/9 임계값별 분포를 출력 (저장은 --dry-run과 별개로 계속 수행)",
    )
    args = parser.parse_args()

    snapshots = collect_history(args.days)

    if not args.dry_run:
        for d, snap_df in snapshots.items():
            save_daily_snapshot(d, snap_df)
        print(f"{len(snapshots)}개 거래일 스냅샷을 data/ 에 저장했습니다.")
    else:
        print(f"(dry-run) {len(snapshots)}개 거래일 스냅샷 준비 완료, 저장은 생략")

    if args.explore_thresholds:
        explore_thresholds(snapshots, candidates=[4, 5, 6, 7, 8])
