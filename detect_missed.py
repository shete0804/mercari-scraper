#!/usr/bin/env python3
"""取りこぼし検知。

今の取得は「検索語の言葉が全部入っている」「番号が合う」など厳しい条件で絞っているので、
タイトルが切れた出品・書き方の違う出品を落とすことがある。ここでは条件をゆるめて
（検索語を短く・SA の表記を問わない・下限を下げる）PayPay とメルカリを探し直し、
「今の最安より安いのに、今の一覧（上位5件）に入っていない出品」だけを Discord に知らせる。

設定（下限・検索語）は書き換えない。偽物・別のカードも混ざるので、最後は人が URL を見て決める。

必要な環境変数: DISCORD_WEBHOOK_URL（なければ送らずに画面に出すだけ）
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import mercari_scraper as ms

ROOT = pathlib.Path(__file__).resolve().parent
SEEN_PATH = ROOT / "results" / "detect_seen.json"
LATEST_PATH = ROOT / "results" / "detect_latest.csv"
PAYPAY_CSV = "https://raw.githubusercontent.com/shete0804/paypayfleamarket-price-tracker/main/results/paypay.csv"
SNKR_CSV = "https://raw.githubusercontent.com/shete0804/poke-price-site/main/results/snkrdunk_latest.csv"
LOWER_RATIO = 0.4        # 3サイトの今の最安の最小値のこの割合より安いものは、偽物とみなして出さない
SEEN_KEEP_DAYS = 30
PAYPAY_OK_CONDITIONS = {"new", "used10", "used20", "used40"}
PAYPAY_WAIT_SEC = 4
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
JST = timezone(timedelta(hours=9))
NAME_KEY = lambda s: re.sub(r"[\s　]", "", s.replace("＆", "&")).lower()  # noqa: E731


def read_csv_url(url: str) -> list[dict]:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def current_tops(rows: list[dict]) -> tuple[dict[str, int], dict[str, set[str]]]:
    """カードごとの今の最安と、今の一覧に載っている URL。"""
    top: dict[str, int] = {}
    urls: dict[str, set[str]] = {}
    for row in rows:
        key = NAME_KEY(row["カード"])
        urls.setdefault(key, set()).add(row["URL"])
        if row["価格"].isdigit():
            top[key] = min(top.get(key, 10**9), int(row["価格"]))
    return top, urls


def short_keyword(rule: ms.CardRule) -> str:
    tokens = rule.keywords[0].split()
    return " ".join(tokens[:2]) if len(tokens) > 1 else tokens[0]

def strict_pass(rule: ms.CardRule, title: str) -> bool:
    """今の取得（本番）の名前の判定を通るか。通るものは本番が拾う側なので、検知の対象にしない。"""
    return any(ms.keyword_fragments_in_name(kw, title) and ms.name_passes(title, rule) for kw in rule.keywords)


def number_in_title(number: str, title: str) -> bool:
    """カード番号（095/069 や 175/XY-P）が題名に書いてあるか（空白・全角の違いは無視）。"""
    norm = lambda s: re.sub(r"\s+", "", s.replace("／", "/")).upper()  # noqa: E731
    return norm(number) in norm(title)


def medium_pass(rule: ms.CardRule, title: str) -> bool:
    """本番より少しゆるい判定。そのカードらしいものだけ残す。
    番号があるカード：番号が題名に書いてある、または題名が「…」で切れている（番号が読めない）もの。
    番号がないカード：検索語の言葉が全部ある（SA の判定は外す）もの。"""
    if not ms.name_passes(title, rule, check_sa=False):
        return False
    if ms.squash(rule.keywords[0].split()[0]) not in ms.squash(title):
        return False
    if rule.number:
        return number_in_title(rule.number, title) or title.rstrip().endswith("…")
    return all(ms.squash(t) in ms.squash(title) for t in short_keyword(rule).split())


def paypay_search(keyword: str, min_price: int) -> list[dict]:
    url = "https://paypayfleamarket.yahoo.co.jp/search/" + requests.utils.quote(keyword, safe="")
    r = requests.get(
        url,
        params={"minPrice": min_price, "sort": "price", "order": "asc", "open": 1},
        headers={"User-Agent": UA, "Accept-Language": "ja"},
        timeout=30,
    )
    r.raise_for_status()
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise RuntimeError("検索ページに __NEXT_DATA__ が無い")
    items: list[dict] = []
    seen: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            if o.get("id") and o.get("title") and o.get("price") is not None and o["id"] not in seen:
                seen.add(o["id"])
                items.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    return items


def paypay_recent(item: dict) -> bool:
    try:
        opened = datetime.fromisoformat(str(item["openTime"]).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return False
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    return opened >= datetime.now(timezone.utc) - timedelta(days=ms.RECENT_DAYS)


def detect_paypay(rule, keyword, floor_min, top, listed) -> list[dict]:
    out = []
    for it in paypay_search(keyword, floor_min):
        cond = (it.get("condition") or {}).get("key") if isinstance(it.get("condition"), dict) else it.get("condition")
        price = int(it["price"])
        url = f"https://paypayfleamarket.yahoo.co.jp/item/{it['id']}"
        if cond not in PAYPAY_OK_CONDITIONS or not paypay_recent(it) or url in listed:
            continue
        if top is not None and price >= top:
            continue
        if not medium_pass(rule, it["title"]) or strict_pass(rule, it["title"]):
            continue
        out.append({"site": "PayPay", "card": rule.name, "price": price, "title": it["title"][:50], "url": url,
                    "now_top": top})
    return out


async def detect_mercari(m, rule, keyword, floor_min, top, listed) -> list[dict]:
    out = []
    items = await ms.with_retry(f"検知 {rule.name}", lambda: ms.search_window(m, keyword, floor_min))
    for it in items:
        if not ms.is_on_sale(it) or ms.is_auction(it) or not ms.is_recent(it):
            continue
        url = (f"https://jp.mercari.com/item/{it.id_}" if it.id_.startswith("m")
               else f"https://jp.mercari.com/shops/product/{it.id_}")
        if url in listed or it.price < floor_min or it.price > ms.MAX_PRICE:
            continue
        if top is not None and it.price >= top:
            continue
        if not medium_pass(rule, it.name) or strict_pass(rule, it.name):
            continue
        out.append({"site": "メルカリ", "card": rule.name, "price": it.price, "title": it.name[:50], "url": url,
                    "now_top": top})
    return out


def send_discord(text: str) -> None:
    hook = ms.DISCORD_WEBHOOK_URL
    if not hook:
        print(text)
        return
    for i in range(0, len(text), 1800):
        requests.post(hook, json={"content": text[i:i + 1800]}, timeout=15).raise_for_status()
        time.sleep(1)


async def main() -> int:
    pp_rows = read_csv_url(PAYPAY_CSV)
    sn_rows = read_csv_url(SNKR_CSV)
    mc_rows = list(csv.DictReader((ROOT / "results" / "mercari.csv").open(encoding="utf-8", newline="")))
    pp_top, pp_urls = current_tops(pp_rows)
    mc_top, mc_urls = current_tops(mc_rows)
    sn_top, _ = current_tops(sn_rows)

    seen: dict[str, str] = {}
    if SEEN_PATH.exists():
        seen = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    cutoff = (datetime.now(JST) - timedelta(days=SEEN_KEEP_DAYS)).strftime("%Y-%m-%d")
    seen = {u: d for u, d in seen.items() if d >= cutoff}
    today = datetime.now(JST).strftime("%Y-%m-%d")

    m = ms.PagedMercapi()
    found: list[dict] = []
    errors: list[str] = []
    for rule in ms.CARDS:
        key = NAME_KEY(rule.name)
        refs = [v for v in (pp_top.get(key), mc_top.get(key), sn_top.get(key)) if v]
        if not refs:
            continue
        floor_min = max(int(min(refs) * LOWER_RATIO), int(max(rule.floor, rule.floor_second) * 0.6))
        kw = short_keyword(rule)
        try:
            found += await detect_mercari(m, rule, kw, floor_min, mc_top.get(key), mc_urls.get(key, set()))
        except Exception as err:  # noqa: BLE001
            errors.append(f"メルカリ {rule.name}: {type(err).__name__}: {err}")
        try:
            found += detect_paypay(rule, kw, floor_min, pp_top.get(key), pp_urls.get(key, set()))
        except Exception as err:  # noqa: BLE001
            errors.append(f"PayPay {rule.name}: {type(err).__name__}: {err}")
        time.sleep(PAYPAY_WAIT_SEC)

    # 同じ出品が複数の検索で出ても1件にする。前に知らせたものは出さない
    uniq: dict[str, dict] = {}
    for f in found:
        uniq.setdefault(f["url"], f)
    new = [f for u, f in uniq.items() if u not in seen]

    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LATEST_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["検知日", "サイト", "カード", "価格", "今の最安", "題名", "URL"])
        for f in sorted(uniq.values(), key=lambda x: (x["card"], x["price"])):
            w.writerow([today, f["site"], f["card"], f["price"], f["now_top"] or "", f["title"], f["url"]])
    for f in new:
        seen[f["url"]] = today
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"取りこぼし候補 {len(new)} 件（今の最安より安く、今の一覧に無いもの。偽物・別カードも混ざります）"]
    for f in sorted(new, key=lambda x: (x["card"], x["price"])):
        now = f"¥{f['now_top']:,}" if f["now_top"] else "なし"
        lines.append(f"・{f['card']} / {f['site']} ¥{f['price']:,}（今の最安 {now}）{f['title']}\n  {f['url']}")
    if errors:
        lines.append(f"検索に失敗 {len(errors)} 件: " + " / ".join(errors[:5]))
    if new or errors:
        send_discord("\n".join(lines))
    else:
        print("新しい候補はありません")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
