import asyncio
import json
import os
import re
from datetime import datetime
from typing import List, Dict
import requests

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Install with: pip install playwright")
    exit(1)

MEGA_CARDS = [
    {"name": "メガルカリオex", "rarity": "MUR", "number": "092/063", "pack": "M1L"},
    {"name": "リーリエの決心", "rarity": "SAR", "number": "091/063", "pack": "M1L"},
    {"name": "メガサーナイトex", "rarity": "MUR", "number": "092/080", "pack": "M1S"},
    {"name": "メガサーナイトex", "rarity": "SAR", "number": "087/063", "pack": "M1S"},
    {"name": "メガリザードンXex", "rarity": "MUR", "number": "116/080", "pack": "M2"},
    {"name": "メガリザードンXex", "rarity": "SAR", "number": "110/080", "pack": "M2"},
    {"name": "メガカイリューex", "rarity": "MUR", "number": "250/193", "pack": "M2a"},
    {"name": "ピカチュウex", "rarity": "SAR", "number": "234/193", "pack": "M2a"},
    {"name": "ロケット団のミュウツーex", "rarity": "SAR", "number": "237/193", "pack": "M2a"},
    {"name": "メガゲンガーex", "rarity": "SAR", "number": "240/193", "pack": "M2a"},
    {"name": "メガカイリューex", "rarity": "SAR", "number": "246/193", "pack": "M2a"},
    {"name": "メガジガルデex", "rarity": "MUR", "number": "117/080", "pack": "M3"},
    {"name": "ニャースex", "rarity": "SAR", "number": "114/080", "pack": "M3"},
    {"name": "メイのはげまし", "rarity": "SAR", "number": "115/080", "pack": "M3"},
    {"name": "メガゲッコウガex", "rarity": "MUR", "number": "120/083", "pack": "M4"},
    {"name": "メガゲッコウガex", "rarity": "SAR", "number": "114/083", "pack": "M4"},
    {"name": "メガダークライex", "rarity": "MUR", "number": "118/081", "pack": "M5"},
    {"name": "メガダークライex", "rarity": "SAR", "number": "114/081", "pack": "M5"},
]

async def search_mercari(card_name: str) -> List[Dict]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            search_url = f"https://jp.mercari.com/search?keyword={card_name}&status=on_sale&sort_order=price_asc"
            
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            items = await page.query_selector_all('[data-testid*="item"]')
            
            results = []
            for item in items[:5]:
                try:
                    price_elem = await item.query_selector('div[class*="price"]')
                    if price_elem:
                        price_text = await price_elem.inner_text()
                        price = re.sub(r'[^\d]', '', price_text)
                        
                        link_elem = await item.query_selector('a')
                        if link_elem:
                            url = await link_elem.get_attribute('href')
                            
                            if price and url:
                                results.append({
                                    "price": int(price),
                                    "url": url if url.startswith('http') else f"https://jp.mercari.com{url}",
                                })
                except Exception as e:
                    continue
            
            await browser.close()
            return sorted(results, key=lambda x: x["price"])[:5]
    
    except Exception as e:
        print(f"Error searching mercari for {card_name}: {e}")
        return []

async def main():
    results = {}
    
    print(f"Starting search at {datetime.now()}")
    
    for card in MEGA_CARDS:
        search_query = f"{card['name']} {card['number']}"
        print(f"Searching: {search_query}")
        
        items = await search_mercari(search_query)
        
        results[f"{card['pack']}_{card['name']}_{card['number']}"] = {
            "card": card,
            "items": items
        }
        
        await asyncio.sleep(2)
    
    return results

def send_to_discord(results: Dict, webhook_url: str):
    embed_list = []
    
    for key, data in results.items():
        card = data["card"]
        items = data["items"]
        
        if items:
            cheapest = min(items, key=lambda x: x["price"])
            
            embed = {
                "title": f"{card['pack']} - {card['name']} ({card['rarity']}) {card['number']}",
                "fields": [
                    {"name": "最安値", "value": f"¥{cheapest['price']:,}", "inline": False},
                    {"name": "商品リンク", "value": f"[メルカリで見る]({cheapest['url']})", "inline": False},
                ],
                "color": 3447003,
                "timestamp": datetime.now().isoformat()
            }
            embed_list.append(embed)
        else:
            embed = {
                "title": f"{card['pack']} - {card['name']} ({card['rarity']}) {card['number']}",
                "description": "販売中の商品が見つかりません",
                "color": 15158332,
                "timestamp": datetime.now().isoformat()
            }
            embed_list.append(embed)
    
    payload = {
        "embeds": embed_list,
        "username": "メルカリ自動検索BOT",
        "avatar_url": "https://cdn-ak.f.st-hatena.com/images/fotolife/m/mercari/20190606/20190606182824.png"
    }
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 204:
            print("Successfully sent to Discord")
        else:
            print(f"Failed to send to Discord: {response.status_code}")
    except Exception as e:
        print(f"Error sending to Discord: {e}")

if __name__ == "__main__":
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        print("Error: DISCORD_WEBHOOK_URL not set")
        exit(1)
    
    results = asyncio.run(main())
    send_to_discord(results, webhook_url)
    
    print(f"Completed at {datetime.now()}")
