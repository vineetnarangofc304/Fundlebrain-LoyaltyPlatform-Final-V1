"""Cleanup QA artefacts created by iteration103 tests (campaigns + marketing DBs)."""
import os
import re
from pathlib import Path

import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
c = Path("/app/memory/test_credentials.md").read_text()
email = re.search(r"(?im)^-\s*Email:\s*`([^`]+)`", c).group(1)
pw = re.search(r"(?im)^-\s*Password:\s*`([^`]+)`", c).group(1)

s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=60)
tok = r.json().get("access_token") or r.json().get("token")
s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})

for camp in s.get(f"{API}/campaigns", timeout=60).json():
    if camp["name"].startswith(("TEST_I103", "QA_I103")):
        d = s.delete(f"{API}/campaigns/{camp['id']}", timeout=60)
        print("campaign", camp["name"], d.status_code, d.text[:120])

mdbs = s.get(f"{API}/marketing-db", timeout=60).json()
rows = mdbs.get("rows") or mdbs.get("items") or (mdbs if isinstance(mdbs, list) else [])
for m in rows:
    if str(m.get("name", "")).startswith("TEST_I103"):
        d = s.delete(f"{API}/marketing-db/{m['id']}", timeout=60)
        print("mdb", m["name"], d.status_code, d.text[:120])

for t in s.get(f"{API}/templates", timeout=60).json()["rows"]:
    if t["name"] == "TEST_bulk_i103":
        print("tpl", t["name"], s.delete(f"{API}/templates/{t['id']}", timeout=60).status_code)
print("done")
