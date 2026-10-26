#!/usr/bin/env python3
"""
メルカリ カード価格モニター（PayPayフリマ版と同じ 13 カード）
==========================================================

対象カードごとにメルカリを検索し、「販売中」かつ「価格の安い順」で候補を読む。
名前・番号・レア度・値段の下限で絞り込み、商品詳細を開いて
販売中・説明文を確かめたものだけ、上位 3 件として Discord に送る。

GitHub Actions から 6 時間ごとに実行される想定。

必要な環境変数:
    DISCORD_WEBHOOK_URL   Discord Incoming Webhook の URL

必要なライブラリ:
    mercapi               メルカリ.jp API ラッパー
    requests              HTTP リクエスト送信
"""

from __future__ import annotations

import asyncio
import csv
import os
import pathlib
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests
from mercapi import Mercapi
from mercapi.requests import SearchRequestData

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

TOP_N = 5
# この値を超える出品は、ダミーや桁の誤りとみなして外す（例：9,999,999 円）
MAX_PRICE = 5_000_000
MAX_RETRIES = 3
RETRY_WAIT_SEC = 5
MAX_PAGES = 10  # 検索結果を読むページ数（1ページ最大120件）。並び替えはできないので、読んだ中から安い順に選ぶ
MAX_DETAIL_CHECKS = 12  # 商品詳細を開いて確かめる上限（カードごと）

# 商品の状態：新品・未使用、未使用に近い、目立った傷や汚れなし、やや傷や汚れあり
# （傷や汚れあり＝5、全体的に状態が悪い＝6 は外す）
CONDITION_IDS: list[int] = [1, 2, 3, 4]

JST = timezone(timedelta(hours=9))


@dataclass
class CardRule:
    """1 枚分の判定ルール（PayPay 版の target.yaml と同じ考え方）。

    keywords:      検索語。1つ目は名前＋レア度・色、2つ目は名前だけ。
    floor:         値段の下限（買取の 8 割など）。両方の検索に付ける。
    floor_second:  2つ目の検索だけに付ける下限（ミュウの色ごと）。
    required:      名前に必要な言葉（例：G/RGB, MUR）。
    exclude_names: 名前にあれば外す言葉（そのカードの別の色など）。
    number:        番号（例：095/069）。別の番号が書いてある出品は外す。番号がない出品は残す。
    sa_required:   名前に SA があるものだけ残す。
    desc_sar:      名前にレア度がない候補は、商品の説明に SAR があるかを確かめる。
    """

    name: str
    keywords: list[str]
    floor: int = 0
    floor_second: int = 0
    required: list[str] = field(default_factory=list)
    exclude_names: list[str] = field(default_factory=list)
    number: str | None = None
    sa_required: bool = False
    desc_sar: bool = False
    # SR の SA 版（SA の表記がない出品）を、カード番号で拾うための番号（例：101/095）
    sa_numbers: list[str] = field(default_factory=list)


# 取引額の上位 14 枚のうち、ピカチュウex（版が未確定のため保留）を除いた 13 枚
CARDS: list[CardRule] = [
    CardRule("緑ミュウ RGB", ["ミュウ G RGB", "ミュウ G RGB"], floor_second=200_000,
             required=["G/RGB"], exclude_names=["R/RGB", "B/RGB"]),
    CardRule("赤ミュウ RGB", ["ミュウ R RGB", "ミュウ R RGB"], floor_second=275_000,
             required=["R/RGB"], exclude_names=["G/RGB", "B/RGB", "緑"]),
    CardRule("青ミュウ RGB", ["ミュウ B RGB", "ミュウ B RGB"], floor_second=210_000,
             required=["B/RGB"], exclude_names=["G/RGB", "R/RGB"]),
    CardRule("ブラッキーVMAX SA", ["ブラッキーVMAX SA", "ブラッキーVMAX HR"], floor=360_000,
             number="095/069", sa_required=True),
    CardRule("メガリザードンXex SAR", ["メガリザードンX SAR", "メガリザードンX"], floor=40_000,
             number="110/080", desc_sar=True),
    CardRule("レックウザVMAX SA", ["レックウザVMAX SA", "レックウザVMAX HR"], floor=300_000,
             number="083/067", sa_required=True),
    CardRule("メガリザードンYex MUR", ["メガリザードンY ex MUR", "メガリザードンY"], floor=90_000,
             required=["MUR"]),
    CardRule("ギラティナV SA", ["ギラティナV SA", "ギラティナV SR"], floor=96_000,
             number="111/100", sa_required=True, sa_numbers=["111/100"]),
    CardRule("ルギアV SA", ["ルギアV SA", "ルギアV SR"], floor=60_000,
             number="110/098", sa_required=True, sa_numbers=["110/098"]),
    CardRule("メガリザードンXex MUR", ["メガリザードンX MUR", "メガリザードンX"], floor=50_000,
             number="116/080", required=["MUR"]),
    CardRule("ミュウVMAX SA", ["ミュウVMAX SA", "ミュウVMAX HR"], floor=72_000,
             number="119", sa_required=True),
    CardRule("メガレックウザex MUR", ["メガレックウザ MUR", "メガレックウザ"], floor=25_000,
             number="113/076", required=["MUR"]),
    CardRule("ニンフィアVMAX SA", ["ニンフィアVMAX SA", "ニンフィアVMAX HR"], floor=76_000,
             number="093/069", sa_required=True),
    CardRule("レッドのピカチュウ", ["レッドのピカチュウ", "レッドのピカチュウ"], floor=64000, number="270/SM-P"),
    CardRule("かんこうきゃく", ["かんこうきゃく", "かんこうきゃく"], floor=100000, number="192/173"),
    CardRule("ピカチュウ 227/S-P", ["ピカチュウ", "ピカチュウ"], floor=160000, required=["227/S-P"]),
    CardRule("ピカチュウ&ゼクロムGX", ["ピカチュウ&ゼクロムGX SA", "ピカチュウ&ゼクロムGX SR"], floor=216000, number="101/095", sa_numbers=["101/095"]),
    CardRule("ブラッキー&ダークライGX", ["ブラッキー&ダークライGX SA", "ブラッキー&ダークライGX SR"], floor=112000, number="182/173", sa_numbers=["182/173"]),
    CardRule("イーブイ", ["イーブイ", "イーブイ"], floor=160000, exclude_names=["イーブイヒーローズ", "VMAX", "GX"]),
    CardRule("ミュウex 347/190", ["ミュウex", "ミュウex"], floor=32000, number="347/190"),
    CardRule("ミュウex SAR 205/165", ["ミュウex SAR", "ミュウex"], floor=16000, number="205/165"),
    CardRule("ゼクロムex", ["ゼクロムex", "ゼクロムex"], floor=32000, number="174/086", exclude_names=["BW-P", "プロモ"]),
    CardRule("レシラムex", ["レシラムex", "レシラムex"], floor=36000, number="174/086", exclude_names=["BW-P", "プロモ"]),
    CardRule("グレイシアVMAX", ["グレイシアVMAX SA", "グレイシアVMAX HR"], floor=56000, number="091/069",
             exclude_names=["ポルトガル", "フランス", "イタリア", "ドイツ", "スペイン"]),
    CardRule("ルチア", ["ルチア", "ルチア"], floor=104000, number="104/096"),
    CardRule("ピカチュウex 764/742", ["ピカチュウex", "ピカチュウex"], floor=44000, number="764/742"),
    CardRule("ビクティニ", ["ビクティニ", "ビクティニ"], floor=88000),
    CardRule("レックウザV", ["レックウザV", "レックウザV"], floor=48000, number="076/067"),
    CardRule("ピカチュウVMAX", ["ピカチュウVMAX", "ピカチュウVMAX"], floor=40000, number="114/100"),
    CardRule("モクロー", ["モクロー", "モクロー"], floor=112000),
    CardRule("ルザミーネ", ["ルザミーネ", "ルザミーネ"], floor=76000, number="055/050"),
    CardRule("リザードンex SAR", ["リザードンex SAR", "リザードンex"], floor=28000, number="201/165"),
    CardRule("リザードン 25th", ["リザードン", "リザードン"], floor=24000, number="001/025"),
    CardRule("レックウザGX", ["レックウザGX", "レックウザGX"], floor=56000, number="240/150"),
    CardRule("ミュウツーGX", ["ミュウツーGX", "ミュウツーGX"], floor=224000, number="082/072"),
    CardRule("サナ", ["サナ", "サナ"], floor=104000, number="185/171"),
    CardRule("ピカチュウ 175/XY-P", ["ピカチュウ", "ピカチュウ"], floor=240000),
    CardRule("エリカのおもてなし", ["エリカのおもてなし", "エリカのおもてなし"], floor=44000, number="190/173"),
    CardRule("こくばバドレックスVMAX", ["こくばバドレックスVMAX", "こくばバドレックスVMAX"], floor=40000, number="086/070"),
    CardRule("バシャーモVMAX", ["バシャーモVMAX", "バシャーモVMAX"], floor=56000, number="086/070"),
    CardRule("カイリューV", ["カイリューV", "カイリューV"], floor=36000, number="074/067"),
    CardRule("ピカチュウ 061/SM-P", ["ピカチュウ", "ピカチュウ"], floor=200000),
    CardRule("シロナ", ["シロナ", "シロナ"], floor=40000, number="070/066"),
    CardRule("シロナのガブリアスex", ["シロナのガブリアスex", "シロナのガブリアスex"], floor=20000, number="087/063"),
    CardRule("ナンジャモ SAR", ["ナンジャモ", "ナンジャモ"], floor=18000, number="096/071"),
    CardRule("ブースターEX", ["ブースターEX", "ブースターEX"], floor=136000, number="007/032"),
    CardRule("ブラッキーGX", ["ブラッキーGX", "ブラッキーGX"], floor=76000, number="229/150"),
    CardRule("MサーナイトEX", ["MサーナイトEX", "MサーナイトEX"], floor=60000, number="020/032"),
    CardRule("バンギラスV SA", ["バンギラスV SA", "バンギラスV"], floor=20000, number="077/070"),
    # ピカチュウex（スタートデッキ100）は版が決まるまで保留
]

# 2 グループに分けて、GitHub で 1 時間に 4 回動かす（PayPay の target_g1 / target_g2 と同じ分け方）
# 環境変数 CARD_GROUP が "1" か "2" のときは、そのグループのカードだけ読む（空なら全部）
CARD_GROUP_NAMES: dict[str, list[str]] = {
    "1": ["緑ミュウ RGB", "赤ミュウ RGB", "青ミュウ RGB", "ブラッキーVMAX SA", "メガリザードンXex SAR",
          "レックウザVMAX SA", "メガリザードンYex MUR", "ギラティナV SA", "ルギアV SA", "メガリザードンXex MUR",
          "ミュウVMAX SA", "メガレックウザex MUR", "ニンフィアVMAX SA", "レッドのピカチュウ", "かんこうきゃく",
          "ピカチュウ 227/S-P", "ピカチュウ&ゼクロムGX", "ブラッキー&ダークライGX", "イーブイ", "ミュウex 347/190",
          "ミュウex SAR 205/165", "ゼクロムex", "レシラムex", "グレイシアVMAX"],
    "2": ["ルチア", "ピカチュウex 764/742", "ビクティニ", "レックウザV", "ピカチュウVMAX", "モクロー", "ルザミーネ",
          "リザードンex SAR", "リザードン 25th", "レックウザGX", "ミュウツーGX", "サナ", "ピカチュウ 175/XY-P",
          "エリカのおもてなし", "こくばバドレックスVMAX", "バシャーモVMAX", "カイリューV", "ピカチュウ 061/SM-P",
          "シロナ", "シロナのガブリアスex", "ナンジャモ SAR", "ブースターEX", "ブラッキーGX", "MサーナイトEX",
          "バンギラスV SA"],
}
_card_group = os.environ.get("CARD_GROUP", "").strip()
if _card_group in CARD_GROUP_NAMES:
    CARDS = [c for c in CARDS if c.name in CARD_GROUP_NAMES[_card_group]]
# テスト用：環境変数 CARD_ONLY にカード名を入れると、そのカードだけ読む
_card_only = os.environ.get("CARD_ONLY", "").strip()
if _card_only:
    CARDS = [c for c in CARDS if c.name == _card_only]

# どのカードでも名前にあれば外す言葉（セット・スリーブ・PSA など、PayPay 版と同じ）
GLOBAL_EXCLUDE_NAMES: list[str] = [
    "スリーブ", "スリープ", "イラスト", "未開封", "BOX", "ボックス", "ディスプレイ", "フレーム",
    "鑑賞用", "セット", "デッキパーツ", "PSA", "英語版", "韓国語版", "中国語版", "海外版",
    "まとめ売り", "ジャンク", "2枚", "3枚", "4枚", "5枚", "10枚", "20枚", "5パック", "10パック",
    "中国版", "韓国版", "福袋", "構築済みデッキ", "デッキ", "旧裏", "おまけ", "オマケ", "2P", "3P", "4P", "5P",
    "詰め合わせ", "ロット", "メモ帳", "ステッカー", "展示用", "特典", "ブレンダ", "プレイマット",
    "コイン", "タオル", "VSTAR",
]

# 商品の説明文にこの言葉があれば外す（手描き・手書きのイラストカードを外すため）
DESCRIPTION_EXCLUDE: tuple[str, ...] = ("手描き", "手書き")

SA_RE = re.compile(r"(?<![A-Za-z])SA(?![A-Za-z])|スペシャルアート", re.IGNORECASE)
# SA か HR のどちらかの表記があれば合格（sa_required の判定に使う）
SA_OR_HR_RE = re.compile(r"(?<![A-Za-z])(SA|HR)(?![A-Za-z])", re.IGNORECASE)
SAR_RE = re.compile(r"(?<![A-Za-z])SAR(?![A-Za-z])", re.IGNORECASE)
NUMBER_RE = re.compile(r"(\d{1,3})\s*/\s*(\d{1,3})")


class PagedMercapi(Mercapi):
    """検索結果のページを指定できるようにする（mercapi は次のページの番号を返すが、指定の口はない）。

    並び替えの指定は効かない（どの値でも「おすすめ順」になる）ため、ページを読んで自分で並べる。
    """

    page_token = ""

    def _search(self, search_request_data):
        search_request_data.data["pageToken"] = self.page_token
        return super()._search(search_request_data)


@dataclass
class Listing:
    card: str
    price: int
    name: str
    url: str
    thumb: str = ""  # 出品の写真（先頭の1枚）


# ---------------------------------------------------------------------------
# 名前の判定
# ---------------------------------------------------------------------------

def squash(text: str) -> str:
    """空白を取り、小文字にする（比較用）。"""
    return re.sub(r"\s+", "", text).lower()


def term_in_name(term: str, name: str) -> bool:
    """語が商品名にあるか。

    - 「G/RGB」は「G/RGB」「G RGB」の両方を同じとみなす（前後が英字の場合は別の語とみなす）。
    - 英字だけの語（MUR, SA, BOX など）は、前後が英字でない場合だけ一致とみなす。
    - それ以外は、空白を取って比べる。
    """
    if "/" in term:
        left, right = term.split("/", 1)
        pattern = rf"(?<![a-z]){re.escape(left.lower())}\s*/?\s*{re.escape(right.lower())}(?![a-z])"
        return re.search(pattern, name.lower()) is not None
    if re.fullmatch(r"[A-Za-z]+", term):
        return re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", name, re.IGNORECASE) is not None
    return squash(term) in squash(name)


def keyword_fragments_in_name(keyword: str, name: str) -> bool:
    """検索語の言葉（空白で区切ったもの）が全部、商品名にあるか。"""
    return all(squash(fragment) in squash(name) for fragment in keyword.split())


def number_ok(name: str, target: str) -> bool:
    """番号が書いてあるのに、目的の番号がない出品は外す。番号がない出品は残す。"""
    found = NUMBER_RE.findall(name)
    if not found:
        return True
    if "/" in target:
        want_a, want_b = (int(x) for x in target.split("/", 1))
        return any(int(a) == want_a and int(b) == want_b for a, b in found)
    return any(int(a) == int(target) for a, _ in found)


def name_passes(name: str, card: CardRule, check_sa: bool = True) -> bool:
    """カードごとの名前の判定（除外語・必須語・SA・番号）。
    check_sa=False は「X HR」の検索で取れた出品（SA の表記を問わない）に使う。"""
    if any(term_in_name(term, name) for term in GLOBAL_EXCLUDE_NAMES + card.exclude_names):
        return False
    if not all(term_in_name(term, name) for term in card.required):
        return False
    if card.number and not number_ok(name, card.number):
        return False
    # SR 系の SA：SA の表記があるか、SA の番号が書いてある出品だけ残す（通常の SR を外す）
    if check_sa and card.sa_numbers and not (SA_RE.search(name) or any(n in name for n in card.sa_numbers)):
        return False
    return True


# ---------------------------------------------------------------------------
# メルカリ検索
# ---------------------------------------------------------------------------

def is_on_sale(item) -> bool:
    # 検索結果は ITEM_STATUS_ON_SALE、商品詳細は on_sale と表記が違う
    return item.status in ("ITEM_STATUS_ON_SALE", "on_sale")


RECENT_DAYS = 30


def is_recent(item) -> bool:
    """最終更新日が直近 RECENT_DAYS 日以内か（古い出品は外す）。"""
    updated = getattr(item, "updated", None)
    if updated is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return updated >= datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)


def is_auction(item) -> bool:
    """オークション出品は外す（mercapi の結果に auction 情報があれば使う）。"""
    auction = getattr(item, "auction", None)
    return getattr(auction, "id_", None) is not None


async def with_retry(label: str, func):
    """一時的な失敗は MAX_RETRIES 回まで再試行する。"""
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await func()
        except Exception as err:  # noqa: BLE001 - リトライ対象は広く取る
            last_err = err
            print(f"[retry {attempt}/{MAX_RETRIES}] {label}: {type(err).__name__}: {err}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_WAIT_SEC)
    raise RuntimeError(f"{label} を {MAX_RETRIES} 回試行して取得失敗: {last_err}")


async def search_window(m: PagedMercapi, keyword: str, price_min: int) -> list:
    """販売中・下限つきで、結果を MAX_PAGES ページまで読む。"""
    kwargs = {
        "status": [SearchRequestData.Status.STATUS_ON_SALE],
        "item_conditions": CONDITION_IDS,
    }
    if price_min > 0:
        kwargs["price_min"] = price_min

    items: list = []
    complete = False
    m.page_token = ""
    for _ in range(MAX_PAGES):
        results = await m.search(keyword, **kwargs)
        items.extend(results.items)
        next_token = results.meta.next_page_token or ""
        if not next_token or not results.items:
            complete = True
            break
        m.page_token = next_token
    m.page_token = ""
    unique = len({item.id_ for item in items})
    print(
        f"[検索] {keyword} 下限{price_min:,}: {unique} 件を読んだ "
        f"（全体 {results.meta.num_found} 件、全部読んだ={complete}）",
        file=sys.stderr,
    )
    return items


async def scrape_card(m: PagedMercapi, card: CardRule) -> list[Listing]:
    """1 カード分の上位 TOP_N 件を取る。"""
    # 下限は両方の検索に付ける（ミュウは色ごとの下限を、1つ目の検索にも付ける）
    floor = max(card.floor, card.floor_second)
    # 検索語が違うものは、すべて検索する（同じ語の重複だけ外す）
    windows = [(kw, floor) for kw in dict.fromkeys(card.keywords)]

    # 2つの検索を合わせ、どの検索語・下限で見つかったかを覚えておく
    pool: dict[str, tuple[object, str, int]] = {}
    for keyword, floor in windows:
        items = await with_retry(
            f"{card.name} [{keyword}]",
            lambda k=keyword, f=floor: search_window(m, k, f),
        )
        for item in items:
            pool.setdefault(item.id_, (item, keyword, floor))

    listings: list[Listing] = []
    checked = 0
    for item, keyword, floor in sorted(pool.values(), key=lambda t: t[0].price):
        if len(listings) >= TOP_N or checked >= MAX_DETAIL_CHECKS:
            break
        if item.price < floor or item.price > MAX_PRICE or not is_on_sale(item) or is_auction(item) or not is_recent(item):
            continue
        # 「X HR」の検索で取れた出品は、SA の表記を問わない（HR の検索語のときだけ SA の判定を外す）
        is_hr_search = keyword.upper().endswith(" HR")
        if not keyword_fragments_in_name(keyword, item.name) or not name_passes(item.name, card, check_sa=not is_hr_search):
            continue

        checked += 1
        try:
            detail = await m.item(item.id_)
        except Exception as err:  # noqa: BLE001 - 1件の失敗で全体を止めない
            print(f"[skip] 商品詳細の取得に失敗: {item.id_}: {err}", file=sys.stderr)
            continue
        if detail is None or not is_on_sale(detail):
            print(f"[除外] 販売中でない: {item.id_}", file=sys.stderr)
            continue
        if detail.price < floor:
            print(f"[除外] 下限未満: {detail.price} < {floor} {item.id_}", file=sys.stderr)
            continue
        if detail.item_condition is None or detail.item_condition.id_ not in CONDITION_IDS:
            print(f"[除外] 状態が範囲外: {item.id_}", file=sys.stderr)
            continue

        desc = detail.description or ""
        if any(word in desc for word in DESCRIPTION_EXCLUDE):
            print(f"[除外] 説明文に手描き・手書き: {item.id_}", file=sys.stderr)
            continue
        if card.desc_sar and not SAR_RE.search(detail.name) and not SAR_RE.search(desc):
            print(f"[除外] 説明にSARがない: {item.id_}", file=sys.stderr)
            continue

        thumbs = detail.thumbnails or item.thumbnails or []
        listings.append(
            Listing(
                card=card.name,
                price=detail.price,
                name=detail.name,
                url=f"https://jp.mercari.com/item/{detail.id_}",
                thumb=thumbs[0] if thumbs else "",
            )
        )

    print(
        f"[{card.name}] 候補 {len(pool)} 件 / 詳細確認 {checked} 件 / 合格 {len(listings)} 件",
        file=sys.stderr,
    )
    return sorted(listings, key=lambda l: l.price)[:TOP_N]


async def fetch_all() -> tuple[dict[str, list[Listing]], dict[str, str]]:
    """全カードを順に取得する（1 件ずつ、メルカリに負荷をかけないため）。"""
    results: dict[str, list[Listing]] = {}
    errors: dict[str, str] = {}

    m = PagedMercapi()
    for card in CARDS:
        try:
            results[card.name] = await scrape_card(m, card)
            for listing in results[card.name]:
                print(f"[合格] {card.name} {_fmt_price(listing.price)} {listing.name} {listing.url}", file=sys.stderr)
        except Exception as err:  # noqa: BLE001
            errors[card.name] = f"{type(err).__name__}: {err}"

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
    for card in CARDS:
        listings = results.get(card.name, [])
        if listings:
            value = "\n".join(
                f"No.{i} [{_fmt_price(l.price)}]({l.url})" for i, l in enumerate(listings, start=1)
            )
        elif card.name in errors:
            value = f"⚠️ 取得失敗: {errors[card.name][:200]}"
        else:
            value = "該当なし"
        fields.append({"name": card.name, "value": value, "inline": False})

    # Discord は 1 通の文字数に上限（約 6000 字）があるため、4 枚ずつに分けて送る
    chunk = 4
    for start in range(0, len(fields), chunk):
        embed = {
            "title": "メルカリ カード 最安値レポート" + (f"（{start // chunk + 1}）" if len(fields) > chunk else ""),
            "description": f"販売中・最安 {TOP_N} 件 / {_now_jst()}",
            "color": 0xE60012,
            "fields": fields[start:start + chunk],
            "footer": {"text": "1 時間ごと自動実行（グループごと）"},
        }
        _send({"embeds": [embed]})


RESULTS_CSV = pathlib.Path("results/mercari.csv")


def write_csv(results: dict[str, list[Listing]], errors: dict[str, str]) -> None:
    """結果を results/mercari.csv に書き出す（スプレッドシートの IMPORTDATA で読む）。"""
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    now = _now_jst()
    # 今回読んだカード以外の行は、前回のまま残す（グループごとに動くため）
    names = {card.name for card in CARDS}
    kept: list[list[str]] = []
    if RESULTS_CSV.exists():
        with RESULTS_CSV.open(newline="", encoding="utf-8") as f:
            kept = [row for row in list(csv.reader(f))[1:] if row and row[0] not in names]
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["カード", "順位", "価格", "URL", "更新", "写真"])
        writer.writerows(kept)
        for card in CARDS:
            listings = results.get(card.name, [])
            if listings:
                for rank, listing in enumerate(listings, start=1):
                    writer.writerow([card.name, rank, listing.price, listing.url, now, listing.thumb])
            elif card.name in errors:
                writer.writerow([card.name, "", "取得失敗", "", now, ""])
            else:
                writer.writerow([card.name, "", "該当なし", "", now, ""])


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
        results, errors = asyncio.run(fetch_all())
    except Exception:  # noqa: BLE001 - 想定外はすべて Discord に流す
        post_failure("スクレイピング失敗", traceback.format_exc())
        return 1

    # 全カード失敗 = 実質的な失敗として扱う
    if errors and len(errors) == len(CARDS):
        detail = "\n".join(f"- {k}: {v}" for k, v in errors.items())
        post_failure("スクレイピング失敗", detail)
        return 1

    # CSV を先に書く（Discord の通知が失敗しても、結果は残す）
    write_csv(results, errors)
    try:
        post_report(results, errors)
    except Exception:  # noqa: BLE001 - 通知の失敗で止めない
        print("Discord への通知に失敗（CSV は書き出し済み）:\n" + traceback.format_exc(), file=sys.stderr)

    if errors:
        print(f"{len(errors)} 件のカードで取得失敗", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
