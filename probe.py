import asyncio
from mercapi import Mercapi
from mercapi.requests import SearchRequestData

async def main():
    m = Mercapi()
    seen = {}
    for kw in ["ミュウ G RGB", "ピカチュウex", "ブラッキーVMAX"]:
        r = await m.search(kw, status=[SearchRequestData.Status.STATUS_ON_SALE])
        for it in r.items[:40]:
            if it.item_condition_id in seen:
                continue
            d = await m.item(it.id_)
            if d is None or d.item_condition is None:
                continue
            seen[it.item_condition_id] = (d.item_condition.id_, d.item_condition.name)
            print("MAP", it.item_condition_id, d.item_condition.id_, d.item_condition.name, flush=True)
    print("DONE", sorted(seen.items()), flush=True)

asyncio.run(main())
