"""KRX 연동 문제를 진단하기 위한 1회성 스크립트.

get_market_net_purchases_of_equities_by_ticker 가 빈 응답을 반환하는 문제가
날짜 때문인지, 이 함수 자체의 문제인지, 로그인/세션 전반의 문제인지 구분하기 위해
관련 pykrx 함수 여러 개를 순서대로 호출해보고 결과를 출력한다.

GitHub Actions에서: python -m scripts.diagnose_krx
로컬에서: .env에 KRX_ID/KRX_PW를 채운 뒤 동일하게 실행
"""
from __future__ import annotations

from dotenv import load_dotenv
from pykrx import stock

load_dotenv()

from src.collect import check_krx_credentials, resolve_target_date  # noqa: E402


def _try(label: str, fn):
    print(f"\n[{label}]")
    try:
        result = fn()
        print(f"  OK")
        return result
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc}")
        return None


def main() -> None:
    check_krx_credentials()
    date = resolve_target_date()
    print(f"target_date = {date}")

    tickers = _try(
        "1. get_market_ticker_list",
        lambda: stock.get_market_ticker_list(date, market="KOSPI"),
    )
    if tickers is not None:
        print(f"  티커 수: {len(tickers)}")

    ohlcv = _try(
        "2. get_market_ohlcv_by_ticker",
        lambda: stock.get_market_ohlcv_by_ticker(date, market="KOSPI"),
    )
    if ohlcv is not None:
        print(f"  shape={ohlcv.shape}")
        print(ohlcv.head(3))

    for investor in ["전체", "개인", "외국인"]:
        df = _try(
            f"3. get_market_net_purchases_of_equities_by_ticker(investor='{investor}')",
            lambda inv=investor: stock.get_market_net_purchases_of_equities_by_ticker(
                date, date, market="KOSPI", investor=inv
            ),
        )
        if df is not None:
            print(f"  shape={df.shape}, columns={list(df.columns)}")
            print(df.head(3))

    single = _try(
        "4. get_market_trading_value_by_date (단일 종목 005930, 삼성전자)",
        lambda: stock.get_market_trading_value_by_date(date, date, "005930"),
    )
    if single is not None:
        print(f"  shape={single.shape}")
        print(single)


if __name__ == "__main__":
    main()
