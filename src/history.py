"""일별 스냅샷을 레포의 data/ 디렉터리에 저장하고, 최근 N일치를 다시 불러온다.

daily 파이프라인은 매일 실행 후 그날 스냅샷을 data/YYYYMMDD.csv 로 커밋해서 쌓아가고,
Section A(외국인 연속 순매수)/B(추세 전환) 신호 계산은 이렇게 누적된 파일들을
다시 읽어서 롤링 윈도우로 계산한다. (워크플로우가 git commit & push까지 해줘야
다음 실행에서도 히스토리가 이어진다. .github/workflows/daily_report.yml 참고.)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def save_daily_snapshot(target_date: str, df: pd.DataFrame) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{target_date}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_recent_snapshots(
    n_days: int, upto_date: str | None = None
) -> dict[str, pd.DataFrame]:
    """data/ 밑에 쌓인 스냅샷 중 최근 n_days개를 {날짜(YYYYMMDD): DataFrame} 형태로 반환한다.

    히스토리가 n_days보다 적게 쌓여 있으면 있는 만큼만 반환한다
    (파이프라인을 막 시작한 첫 몇 주는 Section A/B가 부분적으로만 채워지는 게 정상이다).
    """
    if not DATA_DIR.exists():
        return {}

    files = sorted(DATA_DIR.glob("*.csv"))
    if upto_date:
        files = [f for f in files if f.stem <= upto_date]
    files = files[-n_days:]

    result: dict[str, pd.DataFrame] = {}
    for f in files:
        try:
            result[f.stem] = pd.read_csv(f, dtype={"종목코드": str}, encoding="utf-8-sig")
        except pd.errors.EmptyDataError:
            print(f"경고: {f.name}이 비어있어 건너뜁니다.")
    return result
