import asyncio, datetime, sys
from mercapi import Mercapi
from mercapi.requests import SearchRequestData

KEYWORD = "ピカチュウ&ゼクロムGX 101/095"
DAYS = 28
MAX_PAGES = 10

async def main():
    m = Mercapi()
    status = getattr(SearchRequestData.Status, "STATUS_SOLD_OUT")
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DAYS)
    res = await m.search(KEYWORD, status=[status])
    total, recent, names = 0, 0, []
    for page in range(MAX_PAGES):
        for item in res.items:
            total += 1
            updated = getattr(item, "updated", None)
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=datetime.timezone.utc)
            if updated is not None and updated >= cutoff:
                recent += 1
                names.append(f"{updated.date()} {item.name} {item.price}")
        if not getattr(res, "next_page_token", None):
            break
        res = await m.search(KEYWORD, status=[status], page_token=res.next_page_token)
    print(f"keyword={KEYWORD}")
    print(f"sold items fetched={total}, updated within {DAYS} days={recent}")
    for n in names[:50]:
        print(n)

asyncio.run(main())
