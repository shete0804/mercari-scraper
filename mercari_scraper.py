#!/usr/bin/env python3
"""
繝｡繝ｫ繧ｫ繝ｪ MEGA 繧ｷ繝ｪ繝ｼ繧ｺ 繧ｫ繝ｼ繝我ｾ｡譬ｼ繝｢繝九ち繝ｼ
=========================================

蟇ｾ雎｡繧ｫ繝ｼ繝峨＃縺ｨ縺ｫ繝｡繝ｫ繧ｫ繝ｪ讀懃ｴ｢繝壹・繧ｸ繧帝幕縺阪√瑚ｲｩ螢ｲ荳ｭ縲阪°縺､縲御ｾ｡譬ｼ縺ｮ螳峨＞鬆・阪〒
荳贋ｽ・3 莉ｶ・医き繝ｼ繝牙錐繝ｻ萓｡譬ｼ繝ｻURL・峨ｒ蜿門ｾ励＠縺ｦ Discord 縺ｫ Embed 蠖｢蠑上〒騾夂衍縺吶ｋ縲・
GitHub Actions 縺九ｉ 6 譎る俣縺斐→縺ｫ螳溯｡後＆繧後ｋ諠ｳ螳壹・
蠢・ｦ√↑迺ｰ蠅・､画焚:
    DISCORD_WEBHOOK_URL   Discord Incoming Webhook 縺ｮ URL

豕ｨ諢・
    繝｡繝ｫ繧ｫ繝ｪ縺ｮ蛻ｩ逕ｨ隕冗ｴ・・閾ｪ蜍輔い繧ｯ繧ｻ繧ｹ・医せ繧ｯ繝ｬ繧､繝斐Φ繧ｰ・峨ｒ遖∵ｭ｢縺励※縺・∪縺吶・    縺ｾ縺・jp.mercari.com 縺ｯ Bot 蟇ｾ遲・(DataDome) 縺梧怏蜉ｹ縺ｪ縺溘ａ縲√ヶ繝ｭ繝・け縺輔ｌ繧・    蜿ｯ閭ｽ諤ｧ縺後≠繧翫∪縺吶よ悽繧ｹ繧ｯ繝ｪ繝励ヨ縺ｯ繝悶Ο繝・け繧呈､懃衍縺励◆繧・Discord 縺ｫ
    縲後Γ繝ｫ繧ｫ繝ｪ蜿門ｾ怜､ｱ謨励阪ｒ騾夂衍縺励※邨ゆｺ・＠縺ｾ縺吶・"""

from __future__ import annotations

import os
import re
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
# 險ｭ螳・# ---------------------------------------------------------------------------

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

CARD_KEYWORDS: list[str] = [
    "繝｡繧ｬ繝ｫ繧ｫ繝ｪ繧ｪex MUR 繝｡繧ｬ繝悶Ξ繧､繝・,
    "繝ｪ繝ｼ繝ｪ繧ｨ縺ｮ豎ｺ蠢・SAR 繝｡繧ｬ繝悶Ξ繧､繝・,
    "繝｡繧ｬ繧ｵ繝ｼ繝翫う繝・x MUR 繝｡繧ｬ繧ｷ繝ｳ繝輔か繝九い",
    "繝｡繧ｬ繧ｵ繝ｼ繝翫う繝・x SAR 繝｡繧ｬ繧ｷ繝ｳ繝輔か繝九い",
    "繝｡繧ｬ繝ｪ繧ｶ繝ｼ繝峨ΦXex MUR 繧､繝ｳ繝輔ぉ繝ｫ繝珊",
    "繝｡繧ｬ繝ｪ繧ｶ繝ｼ繝峨ΦXex SAR 繧､繝ｳ繝輔ぉ繝ｫ繝珊",
    "繝｡繧ｬ繧ｫ繧､繝ｪ繝･繝ｼex MUR MEGA繝峨Μ繝ｼ繝ex",
    "繝斐き繝√Η繧ｦex SAR MEGA繝峨Μ繝ｼ繝ex",
    "繝ｭ繧ｱ繝・ヨ蝗｣縺ｮ繝溘Η繧ｦ繝・・ex SAR MEGA繝峨Μ繝ｼ繝ex",
    "繝｡繧ｬ繧ｲ繝ｳ繧ｬ繝ｼex SAR MEGA繝峨Μ繝ｼ繝ex",
    "繝｡繧ｬ繧ｫ繧､繝ｪ繝･繝ｼex SAR MEGA繝峨Μ繝ｼ繝ex",
    "繝｡繧ｬ繧ｸ繧ｬ繝ｫ繝㌃x MUR 繝繝九く繧ｹ繧ｼ繝ｭ",
    "繝九Ε繝ｼ繧ｹex SAR 繝繝九く繧ｹ繧ｼ繝ｭ",
    "繝｡繧､縺ｮ縺ｯ縺偵∪縺・SAR 繝繝九く繧ｹ繧ｼ繝ｭ",
    "繝｡繧ｬ繧ｲ繝・さ繧ｦ繧ｬex MUR 繝九Φ繧ｸ繝｣繧ｹ繝斐リ繝ｼ",
    "繝｡繧ｬ繧ｲ繝・さ繧ｦ繧ｬex SAR 繝九Φ繧ｸ繝｣繧ｹ繝斐リ繝ｼ",
    "繝｡繧ｬ繝繝ｼ繧ｯ繝ｩ繧､ex MUR 繧｢繝薙せ繧｢繧､",
    "繝｡繧ｬ繝繝ｼ繧ｯ繝ｩ繧､ex SAR 繧｢繝薙せ繧｢繧､",
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

# 髯､螟悶く繝ｼ繝ｯ繝ｼ繝会ｼ医そ繝・ヨ雋ｩ螢ｲ縲∬､・焚譫夊ｲｩ螢ｲ縺ｪ縺ｩ・・EXCLUDE_KEYWORDS: list[str] = [
    "繧ｻ繝・ヨ",
    "2譫・,
    "3譫・,
    "4譫・,
    "5譫・,
    "10譫・,
    "20譫・,
    "5繝代ャ繧ｯ",
    "10繝代ャ繧ｯ",
    "Box",
    "繝懊ャ繧ｯ繧ｹ",
    "縺ｾ縺ｨ繧∝｣ｲ繧・,
    "遖剰｢・,
    "讒狗ｯ画ｸ医∩繝・ャ繧ｭ",
    "繝・ャ繧ｭ",
    "譌ｧ陬・,
    "縺翫∪縺・,
    "2P",
    "3P",
    "4P",
    "5P",
]

# status=on_sale・郁ｲｩ螢ｲ荳ｭ縺ｮ縺ｿ・・# 荳ｦ縺ｳ鬆・・繝懊ち繝ｳ繧ｯ繝ｪ繝・け縺ｧ蜍慕噪縺ｫ險ｭ螳・SEARCH_URL_TEMPLATE = (
    "https://jp.mercari.com/search?keyword={keyword}&status=on_sale"
)


class MercariBlockedError(RuntimeError):
    """繝｡繝ｫ繧ｫ繝ｪ縺ｮ Bot 蟇ｾ遲悶〒繧｢繧ｯ繧ｻ繧ｹ縺後ヶ繝ｭ繝・け縺輔ｌ縺溷ｴ蜷医↓騾∝・縺吶ｋ縲・""


@dataclass
class Listing:
    card: str
    price: int
    url: str


# ---------------------------------------------------------------------------
# 繧ｹ繧ｯ繝ｬ繧､繝斐Φ繧ｰ
# ---------------------------------------------------------------------------

def build_search_url(keyword: str) -> str:
    return SEARCH_URL_TEMPLATE.format(keyword=urllib.parse.quote(keyword))


def looks_blocked(page: Page) -> bool:
    """DataDome / CAPTCHA 縺ｪ縺ｩ縲√ヶ繝ｭ繝・け譎ゅ↓迴ｾ繧後ｋ迚ｹ蠕ｴ繧呈､懷・縺吶ｋ縲・""
    if any(token in page.url.lower() for token in ("captcha", "datadome")):
        return True

    body = page.content().lower()
    markers = (
        "captcha-delivery.com",
        "geo.captcha-delivery.com",
        "please enable javascript and cookies",
        "繧｢繧ｯ繧ｻ繧ｹ縺碁寔荳ｭ縺励※縺・∪縺・,
    )
    return any(marker in body for marker in markers)


def is_single_card(title: str) -> bool:
    """繧ｿ繧､繝医Ν縺九ｉ繧ｷ繝ｳ繧ｰ繝ｫ繧ｫ繝ｼ繝峨°縺ｩ縺・°蛻､螳壹☆繧九・
    繧ｻ繝・ヨ雋ｩ螢ｲ繧・､・焚譫夊ｲｩ螢ｲ縲√ち繧､繝医Ν隧先ｬｺ繧帝勁螟悶☆繧九・    """
    title_lower = title.lower()

    # 髯､螟悶Ρ繝ｼ繝・    exclude_words = (
        "繧ｻ繝・ヨ",
        "縺ｾ縺ｨ繧∝｣ｲ繧・,
        "遖剰｢・,
        "隧ｰ繧∝粋繧上○",
        "縺ｾ縺ｨ繧・,
        "3譫・,
        "2譫・,
        "4譫・,
        "5譫・,
        "10譫・,
        "20譫・,
        "繝ｭ繝・ヨ",
        "繧ｹ繝ｪ繝ｼ繝紋ｻ倥″",  # 隍・焚譫壹・蜿ｯ閭ｽ諤ｧ
    )

    # 繧ｿ繧､繝医Ν縺ｫ髯､螟悶Ρ繝ｼ繝峨′蜷ｫ縺ｾ繧後※縺・↑縺・°遒ｺ隱・    for word in exclude_words:
        if word in title_lower:
            return False

    return True


def parse_listings(page: Page, card: str) -> list[Listing]:
    """讀懃ｴ｢邨先棡繝壹・繧ｸ縺ｮ蜈磯ｭ縺九ｉ譛螟ｧ TOP_N 莉ｶ繧貞叙繧雁・縺吶・
    繧ｻ繝ｬ繧ｯ繧ｿ縺ｯ繝｡繝ｫ繧ｫ繝ｪ縺ｮ DOM 螟画峩縺ｧ螢翫ｌ繧・☆縺・・縺ｧ縲∝ｮ滄圀縺ｮ繝壹・繧ｸ繧・    遒ｺ隱阪＠縺ｦ隱ｿ謨ｴ縺吶ｋ縺薙→・・evTools 縺ｧ item-cell / price 繧堤｢ｺ隱搾ｼ峨・    """
    page.wait_for_selector('[data-testid="item-cell"]', timeout=NAV_TIMEOUT_MS)
    cells = page.locator('[data-testid="item-cell"]')

    results: list[Listing] = []
    processed = 0

    for i in range(cells.count()):
        if len(results) >= TOP_N:
            break

        cell = cells.nth(i)

        # 繧ｿ繧､繝医Ν繧貞叙蠕・        title_elem = cell.locator('[class*="title"], h2, [data-testid*="title"]').first
        title = title_elem.inner_text() if title_elem.is_visible() else ""

        # 繧ｷ繝ｳ繧ｰ繝ｫ繧ｫ繝ｼ繝牙愛螳・        if not is_single_card(title):
            processed += 1
            continue

        href = cell.locator("a").first.get_attribute("href") or ""
        if href.startswith("/"):
            href = "https://jp.mercari.com" + href

        # 萓｡譬ｼ繧貞叙蠕暦ｼ亥ｮ滄圀縺ｮ繧ｻ繝ｬ繧ｯ繧ｿ縺ｧ遒ｺ螳溘↓・・        try:
            # 繝｡繝ｫ繧ｫ繝ｪ縺ｮ螳滄圀縺ｮ繧ｻ繝ｬ繧ｯ繧ｿ: span.merPrice 縺ｾ縺溘・ [class*="priceContainer"]
            price_elem = cell.locator('span.merPrice').first
            if not price_elem.is_visible():
                # 繝輔か繝ｼ繝ｫ繝舌ャ繧ｯ
                price_elem = cell.locator('[class*="priceContainer"]').first
            if not price_elem.is_visible():
                continue
            price_text = price_elem.inner_text().strip()
            # ﾂ･\n9,999 縺ｮ蠖｢蠑上°繧画焚蟄励□縺代ｒ謚ｽ蜃ｺ
            match = re.search(r'(\d+(?:,\d+)*)', price_text)
            if not match:
                continue
            price = int(match.group(1).replace(',', ''))
        except Exception:
            continue

        results.append(Listing(card=card, price=price, url=href))
        processed += 1

    return results


def scrape_card(page: Page, keyword: str) -> list[Listing]:
    """1 繧ｫ繝ｼ繝牙・繧呈怙螟ｧ MAX_RETRIES 蝗槭Μ繝医Λ繧､縺励※蜿門ｾ励☆繧九・""
    last_err: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(
                build_search_url(keyword),
                wait_until="networkidle",
                timeout=NAV_TIMEOUT_MS,
            )

            if looks_blocked(page):
                raise MercariBlockedError(f"繝悶Ο繝・け繧呈､懃衍 (keyword={keyword!r})")

            # 騾壼ｸｸ蜃ｺ蜩・ｼ医が繝ｼ繧ｯ繧ｷ繝ｧ繝ｳ髯､螟厄ｼ峨↓繝輔ぅ繝ｫ繧ｿ
            try:
                normal_sale_checkbox = page.locator(
                    'input[type="checkbox"][value*="B38F1DC"], '
                    'label:has-text("騾壼ｸｸ蜃ｺ蜩・) >> input'
                ).first
                if normal_sale_checkbox.is_visible():
                    normal_sale_checkbox.click()
                    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
            except Exception:
                pass

            # 荳ｦ縺ｳ鬆・ｒ縲悟ｮ峨＞鬆・阪↓遒ｺ螳溘↓險ｭ螳・            try:
                sort_button = page.locator(
                    'button:has-text("萓｡譬ｼ"), [data-testid*="sort"]'
                ).first
                if sort_button.is_visible():
                    sort_button.click()
                    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
            except Exception:
                pass

            return parse_listings(page, keyword)

        except MercariBlockedError:
            raise
        except Exception as err:  # noqa: BLE001 - 繝ｪ繝医Λ繧､蟇ｾ雎｡縺ｯ蠎・￥蜿悶ｋ
            last_err = err
            print(
                f"[retry {attempt}/{MAX_RETRIES}] {keyword}: {err}",
                file=sys.stderr,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SEC)

    raise RuntimeError(f"{keyword!r} 繧・{MAX_RETRIES} 蝗櫁ｩｦ陦後＠縺ｦ蜿門ｾ怜､ｱ謨・ {last_err}")


def fetch_all() -> tuple[dict[str, list[Listing]], dict[str, str]]:
    """蜈ｨ繧ｫ繝ｼ繝峨ｒ鬆・↓蜿門ｾ励☆繧九ゅヶ繝ｭ繝・け讀懃衍譎ゅ・蜊ｳ蠎ｧ縺ｫ萓句､悶ｒ騾∝・縺吶ｋ縲・""
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
# Discord 騾夂衍
# ---------------------------------------------------------------------------

def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def _fmt_price(price: int) -> str:
    return f"ﾂ･{price:,}"


def _send(payload: dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 譛ｪ險ｭ螳壹・縺溘ａ騾∽ｿ｡繧偵せ繧ｭ繝・・", file=sys.stderr)
        return
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()


def post_report(results: dict[str, list[Listing]], errors: dict[str, str]) -> None:
    """繧ｫ繝ｼ繝峨＃縺ｨ縺ｫ譛螳・TOP_N 莉ｶ繧偵∪縺ｨ繧√◆ Embed 繧・1 騾夐√ｋ縲・""
    fields = []
    for keyword in CARD_KEYWORDS:
        listings = results.get(keyword, [])
        if listings:
            value = "\n".join(
                f"[{_fmt_price(l.price)}]({l.url})" for l in listings
            )
        elif keyword in errors:
            value = f"笞・・蜿門ｾ怜､ｱ謨・ {errors[keyword][:200]}"
        else:
            value = "雋ｩ螢ｲ荳ｭ縺ｮ蜃ｺ蜩√↑縺・
        fields.append({"name": keyword, "value": value, "inline": False})

    embed = {
        "title": "繝｡繝ｫ繧ｫ繝ｪ MEGA 繧ｷ繝ｪ繝ｼ繧ｺ 譛螳牙､繝ｬ繝昴・繝・,
        "description": f"雋ｩ螢ｲ荳ｭ繝ｻ譛螳・{TOP_N} 莉ｶ / {_now_jst()}",
        "color": 0xE60012,
        "fields": fields[:25],  # Discord 縺ｮ Embed field 荳企剞
        "footer": {"text": "6 譎る俣縺斐→閾ｪ蜍募ｮ溯｡・},
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
# 繧ｨ繝ｳ繝医Μ繝昴う繝ｳ繝・# ---------------------------------------------------------------------------

def main() -> int:
    if not DISCORD_WEBHOOK_URL:
        print("迺ｰ蠅・､画焚 DISCORD_WEBHOOK_URL 縺悟ｿ・ｦ√〒縺・, file=sys.stderr)
        return 1

    try:
        results, errors = fetch_all()
    except MercariBlockedError as err:
        post_failure(
            "繝｡繝ｫ繧ｫ繝ｪ蜿門ｾ怜､ｱ謨・,
            f"{err}\n\nBot 蟇ｾ遲・(DataDome/CAPTCHA) 縺ｫ繧医ｊ繝悶Ο繝・け縺輔ｌ縺溷庄閭ｽ諤ｧ縺後≠繧翫∪縺吶・,
        )
        return 1
    except Exception:  # noqa: BLE001 - 諠ｳ螳壼､悶・縺吶∋縺ｦ Discord 縺ｫ豬√☆
        post_failure("繧ｹ繧ｯ繝ｬ繧､繝斐Φ繧ｰ螟ｱ謨・, traceback.format_exc())
        return 1

    # 蜈ｨ繧ｫ繝ｼ繝牙､ｱ謨・= 螳溯ｳｪ逧・↑螟ｱ謨励→縺励※謇ｱ縺・    if errors and len(errors) == len(CARD_KEYWORDS):
        detail = "\n".join(f"- {k}: {v}" for k, v in errors.items())
        post_failure("繧ｹ繧ｯ繝ｬ繧､繝斐Φ繧ｰ螟ｱ謨・, detail)
        return 1

    post_report(results, errors)

    if errors:
        print(f"{len(errors)} 莉ｶ縺ｮ繧ｫ繝ｼ繝峨〒蜿門ｾ怜､ｱ謨・, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
