import asyncio
from mercapi import Mercapi
from mercapi.requests import SearchRequestData

class P(Mercapi):
    sort_v = "SORT_SCORE"
    order_v = "ORDER_DESC"

    def _search(self, r):
        c = r.data["searchCondition"]
        c["sort"] = self.sort_v
        c["order"] = self.order_v
        return super()._search(r)

async def main():
    combos = [("SORT_PRICE", "ORDER_ASC"), ("SORT_PRICE", "ASC"), ("PRICE", "ORDER_ASC"), ("SORT_PRICE", "ORDER_DESC")]
    for s, o in combos:
        m = P(); m.sort_v = s; m.order_v = o
        r = await m.search("ミュウ G RGB", status=[SearchRequestData.Status.STATUS_ON_SALE])
        print("COMBO", s, o, [i.price for i in r.items[:8]], flush=True)
    m = P(); m.sort_v = "SORT_PRICE"; m.order_v = "ORDER_ASC"
    r = await m.search("ミュウ G RGB", status=[SearchRequestData.Status.STATUS_ON_SALE])
    for it in r.items[:3]:
        print("SEARCH", it.id_, repr(it.status), it.price, flush=True)
        d = await m.item(it.id_)
        if d is None:
            print("DETAIL None", flush=True)
        else:
            print("DETAIL", repr(d.status), d.price, d.name[:30], flush=True)

asyncio.run(main())
