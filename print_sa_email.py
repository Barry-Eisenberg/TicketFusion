import json, pathlib
p = pathlib.Path("service_account.json")
assert p.exists(), "service_account.json not found"
print(json.load(p.open())["client_email"])