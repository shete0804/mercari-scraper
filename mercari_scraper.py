#!/usr/bin/env python3
"""
メルカリ MEGA シリーズ カード価格モニター
=========================================

対象カードごとにメルカリ検索ページを開き、「販売中」かつ「価格の安い順」で
上位 3 件（カード名・価格・URL）を取得して Discord に Embed 形式で通知する。

GitHub Actions から 6 時間ごとに実行される想定。

必要な環境変数:
    DISCORD_WEBHOOK_URL   Discord Incoming Webhook の URL

注意:
    メルカリの利用規約は自動アクセス（スクレイピング）を禁止しています。
    また jp.mercari.com は Bot 対策 (DataDome) が有効なため、ブロックされる
    可能性があります。本スクリプトはブロックを検知したら Discord に
    「メルカリ取得失敗」を通知して終了します。
"""

from __future__ import annotations

import os
import sys
import time
import traceback
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

# TODO: MEGA シリーズ 18 枚の正確なカード名 / 検索キーワードに置き換える。
#       既存の mercari_scraper.py にリストがある場合はそれを移植すること。
CARD_KEYWORDS: list[str] = [
    "MEGA カード名 01",
    "MEGA カード名 02",
    "MEGA カード名 03",
    "MEGA カード名 04",
    "MEGA カード名 05",
    "MEGA カード名 06",
    "MEGA カード名 07",
    "MEGA カード名 08",
    "MEGA カード名 09",
    "MEGA カード名 10",
    "MEGA カード名 11",
    "MEGA カード名 12",
    "MEGA カード名 13",
    "MEGA カード名 14",
    "MEGA カード名 15",
    "MEGA カード名 16",
    "MEGA カード名 17",
    "MEGA カード名 18",
]

TOP_N = 3
MAX_RETRIES = 3
NAV_TIMEOUT_MS = 30_000
RETRY_WAIT_SEC = 5

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

JST = timezone(timedelta(hours=9))

# status=on_sale（販売中のみ） / sort=price&order=asc（価格の安い順）
SEARCH_URL_TEMPLATE = (
    "https://jp.mercari.com/search?keyword={keyword}"
    "&status=on_sale&sort=price&order=asc"
)


class MercariBlockedError(RuntimeError):
    """メルカリの Bot 対策でアクセスがブロックされた場合に送出する。"""


@dataclass
class Listing:
    card: str
    price: int
    url: str


# ---------------------------------------------------------------------------
# スクレイピング
# ---------------------------------------------------------------------------

def build_search_url(keyword: str) -> str:
    return SEARCH_URL_TEMPLATE.format(keyword=urllib.parse.quote(keyword))


def looks_blocked(page: Page) -> bool:
    """DataDome / CAPTCHA など、ブロック時に現れる特徴を検出する。"""
    if any(token in page.url.lower() for token in ("captcha", "datadome")):
        return True

    body = page.content().lower()
    markers = (
        "captcha-delivery.com",
        "geo.captcha-delivery.com",
        "please enable javascript and cookies",
        "アクセスが集中しています",
    )
    return any(marker in body for marker in markers)


def parse_listings(page: Page, card: str) -> list[Listing]:
    """検索結果ページの先頭から最大 TOP_N 件を取り出す。

    セレクタはメルカリの DOM 変更で壊れやすいので、実際のページを
    確認して調整すること（DevTools で item-cell / price を確認）。
    """
    page.wait_for_selector('[data-testid="item-cell"]', timeout=NAV_TIMEOUT_MS)
    cells = page.locator('[data-testid="item-cell"]')

    results: list[Listing] = []
    for i in range(min(cells.count(), TOP_N)):
        cell = cells.nth(i)

        href = cell.locator("a").first.get_attribute("href") or ""
        if href.startswith("/"):
            href = "https://jp.mercari.com" + href

        price_text = cell.locator(
            '[data-testid="price"], [class*="number"]'
        ).first.inner_text()
        digits = "".join(ch for ch in price_text if ch.isdigit())
        if not digits:
            continue

        results.append(Listing(card=card, price=int(digits), url=href))

    return results


def scrape_card(page: Page, keyword: str) -> list[Listing]:
    """1 カード分を最大 MAX_RETRIES 回リトライして取得する。"""
    last_err: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(
                build_search_url(keyword),
                wait_until="networkidle",
                timeout=NAV_TIMEOUT_MS,
            )

            if looks_blocked(page):
                raise MercariBlockedError(f"ブロックを検知 (keyword={keyword!r})")

            return parse_listings(page, keyword)

        except MercariBlockedError:
            raise
        except Exception as err:  # noqa: BLE001 - リトライ対象は広く取る
            last_err = err
            print(
                f"[retry {attempt}/{MAX_RETRIES}] {keyword}: {err}",
                file=sys.stderr,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SEC)

    raise RuntimeError(f"{keyword!r} を {MAX_RETRIES} 回試行して取得失敗: {last_err}")


def fetch_all() -> tuple[dict[str, list[Listing]], dict[str, str]]:
    """全カードを順に取得する。ブロック検知時は即座に例外を送出する。"""
    results: dict[str, list[Listing]] = {}
    errors: dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(NAV_TIMEOUT_MS)

        try:
            for keyword in CARD_KEYWORDS:
                try:
                    results[keyword] = scrape_card(page, keyword)
                except MercariBlockedError:
                    raise
                except Exception as err:  # noqa: BLE001
                    errors[keyword] = str(err)
        finally:
            browser.close()

    return results, errors


# ---------------------------------------------------------------------------
# Discord 通知
# ---------------------------------------------------------------------------

def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def _fmt_price(price: int) -> str:
    return f"¥{price:,}"


def _send(payload: dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 未設定のため送信をスキップ", file=sys.stderr)
        return
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()


def post_report(results: dict[str, list[Listing]], errors: dict[str, str]) -> None:
    """カードごとに最安 TOP_N 件をまとめた Embed を 1 通送る。"""
    fields = []
    for keyword in CARD_KEYWORDS:
        listings = results.get(keyword, [])
        if listings:
            value = "\n".join(
                f"[{_fmt_price(l.price)}]({l.url})" for l in listings
            )
        elif keyword in errors:
            value = f"⚠️ 取得失敗: {errors[keyword][:200]}"
        else:
            value = "販売中の出品なし"
        fields.append({"name": keyword, "value": value, "inline": False})

    embed = {
        "title": "メルカリ MEGA シリーズ 最安値レポート",
        "description": f"販売中・最安 {TOP_N} 件 / {_now_jst()}",
        "color": 0xE60012,
        "fields": fields[:25],  # Discord の Embed field 上限
        "footer": {"text": "6 時間ごと自動実行"},
    }
    _send({"embeds": [embed]})


def post_failure(title: str, detail: str) -> None:
    embed = {
        "title": title,
        "description": f"```\n{detail[:3800]}\n```",
        "color": 0xFF0000,
        "footer": {"text": _now_jst()},
    }
    _send({"embeds": [embed]})


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> int:
    if not DISCORD_WEBHOOK_URL:
        print("環境変数 DISCORD_WEBHOOK_URL が必要です", file=sys.stderr)
        return 1

    try:
        results, errors = fetch_all()
    except MercariBlockedError as err:
        post_failure(
            "メルカリ取得失敗",
            f"{err}\n\nBot 対策 (DataDome/CAPTCHA) によりブロックされた可能性があります。",
        )
        return 1
    except Exception:  # noqa: BLE001 - 想定外はすべて Discord に流す
        post_failure("スクレイピング失敗", traceback.format_exc())
        return 1

    # 全カード失敗 = 実質的な失敗として扱う
    if errors and len(errors) == len(CARD_KEYWORDS):
        detail = "\n".join(f"- {k}: {v}" for k, v in errors.items())
        post_failure("スクレイピング失敗", detail)
        return 1

    post_report(results, errors)

    if errors:
        print(f"{len(errors)} 件のカードで取得失敗", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
