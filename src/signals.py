"""Section A(외국인 연속 순매수), Section B(단순 부호 전환) 신호를 계산한다.

두 함수 모두 history.load_recent_snapshots()가 반환하는
{날짜(YYYYMMDD): DataFrame} 딕셔너리를 입력으로 받는다.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_LOOKBACK = 10
# 2026-09-04, 실제 59거래일 데이터로 롤링 비교한 결과(scripts/backfill_history.py
# --explore-thresholds) threshold=8이 하루 평균 22개(범위 14~32개)로 목표 범위
# (5~30개)에 가장 잘 맞아 이 값으로 확정. 5=평균100개, 6=71개, 7=44개로 너무 많았음.
DEFAULT_STREAK_THRESHOLD = 8

SHORT_WINDOW = 3
LONG_WINDOW = 20


def _panel(history: dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    """{날짜: DataFrame} 을 (종목코드 x 날짜) 피벗 테이블로 합친다."""
    series_list = []
    for date in sorted(history.keys()):
        s = history[date].set_index("종목코드")[column]
        s.name = date
        series_list.append(s)
    return pd.concat(series_list, axis=1).sort_index(axis=1)


def foreign_streak_signals(
    history: dict[str, pd.DataFrame],
    index_close: pd.Series,
    lookback: int = DEFAULT_LOOKBACK,
    threshold: int = DEFAULT_STREAK_THRESHOLD,
) -> pd.DataFrame:
    """최근 lookback거래일 중 threshold일 이상 외국인 순매수(대금 > 0)인 종목.

    수익률로 "효과"를 검증하는 게 아니라, 걸린 종목들의
    (1) 최근 거래대금 변화 추이, (2) 코스피지수 대비 초과 등락률을
    보조지표로 함께 계산해서 판단 재료로 제공한다.
    """
    dates = sorted(history.keys())[-lookback:]
    sub = {d: history[d] for d in dates}
    if len(dates) < 2:
        return pd.DataFrame()

    net_buy = _panel(sub, "외국인_순매수거래대금")
    streak = (net_buy > 0).sum(axis=1)
    flagged = streak[streak >= threshold].index

    trading_value = _panel(sub, "거래대금")
    price = _panel(sub, "종가")
    name = _panel(sub, "종목명")

    idx_return = index_close.loc[dates[-1]] / index_close.loc[dates[0]] - 1

    split = max(len(dates) - 3, 1)  # 최근 3일 vs 그 이전
    rows = []
    for code in flagged:
        recent_vol = trading_value.loc[code].iloc[split:].mean()
        prior_vol = trading_value.loc[code].iloc[:split].mean()
        vol_change = (recent_vol / prior_vol - 1) if prior_vol else float("nan")

        px_series = price.loc[code].dropna()
        px_return = (
            px_series.iloc[-1] / px_series.iloc[0] - 1 if len(px_series) >= 2 else float("nan")
        )

        rows.append(
            {
                "종목코드": code,
                "종목명": name.loc[code].dropna().iloc[-1],
                "순매수일수": int(streak.loc[code]),
                "lookback일수": len(dates),
                f"{len(dates)}일_누적순매수대금": net_buy.loc[code].sum(),
                "거래대금_변화율": vol_change,
                "구간수익률": px_return,
                "지수대비_초과수익률": px_return - idx_return if pd.notna(px_return) else float("nan"),
            }
        )

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(f"{len(dates)}일_누적순매수대금", ascending=False)
    return result


def trend_reversal_signals(
    history: dict[str, pd.DataFrame],
    investor_labels: list[str],
    short_window: int = SHORT_WINDOW,
    long_window: int = LONG_WINDOW,
) -> pd.DataFrame:
    """단순 부호 전환 규칙.

    최근 short_window일 평균 순매수 부호가, 그 이전
    (long_window - short_window)일 평균 순매수 부호와 반대인 종목을 투자자 유형별로 찾는다.
    """
    dates = sorted(history.keys())[-long_window:]
    sub = {d: history[d] for d in dates}
    if len(dates) < short_window + 1:
        return pd.DataFrame()

    name = _panel(sub, "종목명")
    rows = []

    for label in investor_labels:
        panel = _panel(sub, f"{label}_순매수거래대금")
        recent = panel.iloc[:, -short_window:].mean(axis=1)
        prior = panel.iloc[:, :-short_window].mean(axis=1)

        flipped = recent.index[(recent * prior < 0) & recent.notna() & prior.notna()]

        for code in flipped:
            rows.append(
                {
                    "종목코드": code,
                    "종목명": name.loc[code].dropna().iloc[-1],
                    "투자자유형": label,
                    f"최근{short_window}일평균순매수대금": recent.loc[code],
                    f"이전{long_window - short_window}일평균순매수대금": prior.loc[code],
                }
            )

    return pd.DataFrame(rows)
