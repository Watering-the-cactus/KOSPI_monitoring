"""네이버 뉴스 검색(NAVER API HUB) API로 관련 기사를 찾고, Claude API로 요약/코멘트를 생성한다.

2026년 네이버 검색 API가 개발자센터(developers.naver.com)에서 네이버클라우드플랫폼(NCP)의
NAVER API HUB로 이관되었다. 기존 개발자센터 방식은 2027-06-30까지 유예되지만, 이 프로젝트는
계속 운영할 것이므로 처음부터 신규 HUB 방식으로 등록한다.

필요 secrets: NAVER_API_KEY_ID, NAVER_API_KEY (NAVER API HUB, console.ncloud.com 무료 가입),
             ANTHROPIC_API_KEY (console.anthropic.com)
"""
from __future__ import annotations

import os
import re

import requests

NAVER_SEARCH_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-5"

_TAG_RE = re.compile(r"</?b>")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text)


def search_news(query: str, display: int = 5) -> list[dict]:
    """네이버 뉴스 검색(API HUB). 반환 항목: title, description, link, pubDate."""
    headers = {
        "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_API_KEY_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NAVER_API_KEY"],
    }
    params = {"query": query, "display": display, "sort": "sim"}

    resp = requests.get(NAVER_SEARCH_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()

    items = resp.json().get("items", [])
    for item in items:
        item["title"] = _strip_tags(item["title"])
        item["description"] = _strip_tags(item["description"])
    return items


def summarize_stock_news(stock_name: str, reason: str, news_items: list[dict]) -> str:
    """왜 이 종목이 주목받는지(reason)와 최근 뉴스를 근거로 짧은 코멘트를 생성한다."""
    if not news_items:
        return "관련 뉴스를 찾지 못했습니다."

    articles = "\n".join(f"- {item['title']}: {item['description']}" for item in news_items)
    prompt = (
        f"'{stock_name}' 종목이 다음 이유로 매매동향 상 주목받고 있습니다: {reason}\n\n"
        f"관련 최근 뉴스 목록:\n{articles}\n\n"
        "위 정보를 바탕으로 3~4문장 한국어로 다음을 정리해줘: "
        "(1) 이런 매매동향이 나타난 배경으로 추정되는 이슈, "
        "(2) 주요 호재/악재, "
        "(3) 간단한 향후 관전 포인트. "
        "뉴스에 근거가 없는 내용은 단정하지 말고 '~로 추정된다' 같은 표현을 써줘."
    )

    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]
