"""KRX(한국거래소) 데이터를 pykrx로 수집한다.

2025-12-27부로 data.krx.co.kr 정보데이터시스템이 회원제로 전환되어,
환경변수 KRX_ID / KRX_PW 가 설정되어 있어야 정상적으로 데이터를 받아올 수 있다.
(간편가입이 아닌, 아이디/비밀번호를 직접 만드는 방식으로 가입해야 자동 로그인에 쓸 수 있다.)
"""
from __future__ import annotations

import os
import time

import pandas as pd
from pykrx import stock

# 리포트에 표시할 라벨 -> pykrx investor 파라미터 값 매핑
INVESTOR_TYPES = {
    "개인": "개인",
    "기관": "기관합계",
    "외국인": "외국인",
    "기타법인": "기타법인",
}


def check_krx_credentials() -> None:
    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        raise RuntimeError(
            "KRX_ID / KRX_PW 환경변수가 설정되어 있지 않습니다. "
            "data.krx.co.kr에 아이디/비밀번호로 직접 가입한 뒤 "
            "GitHub Actions repo secrets에 등록하세요."
        )


def resolve_target_date() -> str:
    """가장 최근 영업일(YYYYMMDD)을 반환한다.

    주말/공휴일에 실행되더라도 직전 거래일 데이터를 기준으로 리포트를 만들 수 있게 한다.
    """
    return stock.get_nearest_business_day_in_a_week(prev=True)


def collect_investor_net_purchases(date: str, market: str = "KOSPI") -> pd.DataFrame:
    """투자자 유형별 종목별 순매수 데이터를 하나의 DataFrame으로 합친다.

    투자자 유형 하나당 전종목을 한 번에 조회하는 함수를 쓰기 때문에,
    종목 수(800개+)에 관계없이 호출 횟수는 투자자 유형 개수(4번)로 끝난다.
    """
    merged: pd.DataFrame | None = None
    name_map: pd.Series | None = None

    for label, investor in INVESTOR_TYPES.items():
        df = stock.get_market_net_purchases_of_equities_by_ticker(
            date, date, market=market, investor=investor
        )
        if df is None or df.empty:
            raise RuntimeError(f"{label}({investor}) 데이터를 받아오지 못했습니다.")

        df.index.name = "종목코드"

        if name_map is None:
            name_map = df["종목명"]

        renamed = df[["순매수거래량", "순매수거래대금"]].rename(
            columns={
                "순매수거래량": f"{label}_순매수거래량",
                "순매수거래대금": f"{label}_순매수거래대금",
            }
        )
        merged = renamed if merged is None else merged.join(renamed, how="outer")
        time.sleep(0.5)  # 연속 호출 간 짧은 대기 (과도한 연속 요청 방지)

    assert merged is not None and name_map is not None
    merged.insert(0, "종목명", name_map)
    return merged.reset_index()


def collect_price_info(date: str, market: str = "KOSPI") -> pd.DataFrame:
    """종가, 등락률, 거래대금 등 시세 정보를 조회한다."""
    df = stock.get_market_ohlcv_by_ticker(date, market=market)
    df.index.name = "종목코드"
    return df.reset_index()[["종목코드", "종가", "등락률", "거래대금"]]


def collect_all(
    date: str | None = None, market: str = "KOSPI"
) -> tuple[str, pd.DataFrame]:
    """전체 파이프라인에서 쓰는 진입점. (기준일, 병합된 DataFrame)을 반환한다."""
    check_krx_credentials()
    target_date = date or resolve_target_date()

    net_purchases = collect_investor_net_purchases(target_date, market)
    price_info = collect_price_info(target_date, market)

    result = net_purchases.merge(price_info, on="종목코드", how="left")
    return target_date, result


if __name__ == "__main__":
    d, result_df = collect_all()
    print(f"target_date={d}, rows={len(result_df)}")
    print(result_df.head())
