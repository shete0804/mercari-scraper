import inspect, dataclasses
from mercapi.requests import SearchRequestData
from mercapi import Mercapi
print("SearchRequestData fields:")
try:
    print([f.name for f in dataclasses.fields(SearchRequestData)])
except Exception:
    print(inspect.signature(SearchRequestData.__init__))
print("Mercapi.search signature:")
print(inspect.signature(Mercapi.search))
print("Status members:", [s for s in dir(SearchRequestData.Status) if s.startswith("STATUS")])
