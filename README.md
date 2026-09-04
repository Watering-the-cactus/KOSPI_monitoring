# 코스피 투자자별 매매동향 데일리 리포트

코스피 **시가총액 상위 300개** 종목의 개인/기관/외국인/기타법인 순매수 데이터를
매일 장마감 이후 수집해서, 다음날 개장 전(기본 KST 07:30) 이메일로 발송하는
파이프라인입니다.

## 리포트 구성

1. **🎯 탑픽** — 최근 10거래일 중 8일 이상 외국인이 순매수한 종목 중 누적 순매수대금
   상위 20개. 구간수익률/지수대비 초과등락률/거래대금 변화율에 더해, 같은 기간
   개인·기관·기타법인의 누적 순매수도 보조지표로 함께 표시
2. **📰 탑픽 뉴스 & 관전 포인트** — 탑픽 종목에 대해서만 뉴스 검색 + Claude 요약
3. **📊 상세 대시보드** — GitHub Pages에 매일 게시되는 시가총액 상위 300개 정렬/검색 가능한 표

투자자 유형별 순매수/순매도 상위 종목, 외국인 연속매수 전체 리스트, 추세 전환
관찰(보조 신호)은 이메일 본문 대신 **첨부 xlsx의 별도 시트**로만 정리한다
(`전종목`, `외국인연속매수_전체`, `추세전환관찰`,
`개인_TOP`/`기관_TOP`/`외국인_TOP`/`기타법인_TOP`).

## 아키텍처

```
GitHub Actions (매일 KST 07:30, cron)
  └─ src/collect.py     KRX에서 당일 전종목 투자자별 순매수 + 시세 수집 후 시가총액 상위 300개로 축소 (호출 4~5회)
  └─ src/history.py     data/YYYYMMDD.csv 로 저장, 최근 N일치 재로딩
  └─ src/signals.py     외국인 연속매수(탑픽 소스)/추세전환(보조) 계산
  └─ src/news.py        구글 뉴스(RSS) 검색 + Claude API 요약
  └─ src/build_report.py 이메일 본문(HTML) / 첨부(xlsx) / 대시보드(docs/index.html) 생성
  └─ src/send_mail.py   Gmail SMTP로 발송
  └─ (워크플로우) data/, docs/ 를 리포지토리에 커밋 & 푸시
```

`data/`에 매일 스냅샷이 쌓여야 Section A/B가 동작하므로, 파이프라인을 처음 시작할 때는
`scripts/backfill_history.py`로 과거 데이터를 먼저 채워 넣는 걸 권장합니다.

## 필요한 사전 준비

### 1. KRX 계정 (데이터 수집)

2025-12-27부로 data.krx.co.kr이 회원제로 전환되어 로그인이 필요합니다.
**반드시 아이디/비밀번호를 직접 만드는 방식으로 가입**하세요. 네이버/카카오 간편가입은
비밀번호가 없어서 이 파이프라인의 자동 로그인에 쓸 수 없습니다.

### 2. Gmail 앱 비밀번호 (발송)

1. 발송용으로 쓸 Gmail 계정에서 2단계 인증을 켭니다.
2. [Google 계정 > 보안 > 앱 비밀번호](https://myaccount.google.com/apppasswords) 에서
   앱 비밀번호를 발급받습니다.

### 3. 뉴스 검색 — 구글 뉴스 RSS (별도 가입 불필요)

뉴스 소스는 구글 뉴스 RSS(`news.google.com/rss/search`)를 씁니다. API 키 발급이나
계정 가입이 필요 없고, 과금 걱정도 없습니다. 별도로 준비할 게 없습니다.

### 4. Claude API (뉴스 요약)

[console.anthropic.com](https://console.anthropic.com) 에서 API 키를 발급받습니다.
하루 10종목 내외 요약이라 비용은 미미하지만, 유료 API입니다.

### 5. GitHub repo secrets 등록

Settings → Secrets and variables → Actions 에서 아래를 등록합니다.

| 이름 | 용도 |
|---|---|
| `KRX_ID`, `KRX_PW` | KRX 로그인 |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | 발신 |
| `RECIPIENT_EMAIL` | 수신 주소. 쉼표(,) 또는 세미콜론(;)으로 여러 명 지정 가능 (예: `a@x.com, b@y.com`) |
| `ANTHROPIC_API_KEY` | 뉴스 요약 |

Repository variable(Variables 탭)로 `DASHBOARD_BASE_URL`도 등록하면 이메일에
대시보드 링크가 함께 붙습니다 (예: `https://<username>.github.io/<repo>`).

### 6. GitHub Pages 활성화 (대시보드)

Settings → Pages → Source를 `main` 브랜치의 `/docs` 폴더로 지정합니다.
워크플로우가 매일 `docs/index.html`을 갱신 & 커밋하면 자동으로 재게시됩니다.

## 로컬 테스트

```bash
pip install -r requirements.txt
cp .env.example .env   # 값 채우기

# PowerShell 기준으로 .env를 읽어 환경변수로 등록한 뒤
python -m src.main
```

과거 히스토리를 미리 채우거나, 외국인 연속매수 임계값(N)을 점검하고 싶을 때:

```bash
python -m scripts.backfill_history --days 20                       # 최근 20거래일 시딩
python -m scripts.backfill_history --days 60 --dry-run --explore-thresholds  # N=6/7/8/9 분포 비교
```

`--explore-thresholds` 결과(걸린 종목 수, 거래대금 변화율/지수대비 초과등락률 분포)를 보고
`src/signals.py`의 `DEFAULT_STREAK_THRESHOLD` 값을 조정하세요.

## 알려진 리스크 / 확인 필요 사항

- **KRX 구조 변경**: data.krx.co.kr은 비공식 API 성격이라 예고 없이 응답 구조가 바뀔 수 있습니다.
  실제 KRX 계정으로 첫 실행 시 `pykrx.get_market_net_purchases_of_equities_by_ticker` /
  `get_market_trading_value_by_date`의 컬럼명이 코드에서 가정한 것과 일치하는지 확인하세요.
- **뉴스/요약 비용**: `MAX_NEWS_TARGETS`(기본 10)로 하루 뉴스 요약 대상을 제한해서 API 비용을
  통제하고 있습니다. 필요하면 `src/main.py`에서 조정하세요.
- **백필 스크립트 소요 시간**: 코스피 전종목 기준 800회 이상 호출이 필요해서 완료까지
  몇 분 정도 걸립니다. 매일 자동 실행 대상이 아니라 초기 시딩/가끔 점검용입니다.
