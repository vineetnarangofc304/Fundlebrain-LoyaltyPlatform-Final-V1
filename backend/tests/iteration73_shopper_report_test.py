"""Iteration 73 — Shopper Bill Report (bill-level report for everyone who shopped).

Covers the new `/api/shopper-report/*` endpoints:
  * GET /shopper-report/bills          — paginated listing + 22-column contract
  * GET /shopper-report/filter-options — stores + zones for the filter dropdowns
  * GET /shopper-report/export         — streamed CSV (header + rows)

Validates: auth, column contract, date-range / bill-type / sort / pagination filters,
the scale-safe recency path (no exact total, returns has_more), and the CSV export shape.

Run: pytest -q backend/tests/iteration73_shopper_report_test.py
"""
import os
import io
import csv
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "http://localhost:8001/api"

EXPECTED_KEYS = {
    "bill_date", "bill_time", "bill_type", "customer_mobile", "reg_store",
    "store_code", "trans_store_name", "transaction_id", "bill_number",
    "customer_type", "recency", "last_visit", "second_last_visit",
    "total_visits", "zone", "customer_city", "net_before_tax", "total_tax",
    "total_discount", "total_bill_amount", "lifetime_purchase", "lifetime_bill_cuts",
}


async def _token(cli):
    r = await cli.post(f"{BASE}/auth/login",
                       json={"email": "superadmin@fundle.io", "password": "Fundle@2026"})
    return r.json()["token"]


def test_requires_auth():
    async def _run():
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.get(f"{BASE}/shopper-report/bills")
            assert r.status_code in (401, 403), r.status_code
    asyncio.run(_run())


def test_bills_column_contract_and_row_shape():
    async def _run():
        async with httpx.AsyncClient(timeout=60.0) as cli:
            h = {"Authorization": f"Bearer {await _token(cli)}"}
            r = await cli.get(f"{BASE}/shopper-report/bills", params={"limit": 5}, headers=h)
            assert r.status_code == 200, r.text
            d = r.json()
            keys = {c["key"] for c in d["columns"]}
            assert keys == EXPECTED_KEYS, keys ^ EXPECTED_KEYS
            assert d["total"] is None or d["total"] >= len(d["rows"])
            if d["rows"]:
                row = d["rows"][0]
                for k in EXPECTED_KEYS:
                    assert k in row, f"missing {k}"
                assert row["bill_type"] in ("Return", "Regular")
    asyncio.run(_run())


def test_bill_type_filter():
    async def _run():
        async with httpx.AsyncClient(timeout=60.0) as cli:
            h = {"Authorization": f"Bearer {await _token(cli)}"}
            r = await cli.get(f"{BASE}/shopper-report/bills",
                              params={"bill_type": "return", "limit": 10}, headers=h)
            assert r.status_code == 200, r.text
            for row in r.json()["rows"]:
                assert row["bill_type"] == "Return", row
    asyncio.run(_run())


def test_date_range_and_sort():
    async def _run():
        async with httpx.AsyncClient(timeout=60.0) as cli:
            h = {"Authorization": f"Bearer {await _token(cli)}"}
            r = await cli.get(f"{BASE}/shopper-report/bills",
                              params={"start_date": "2000-01-01", "end_date": "2100-01-01",
                                      "sort_by": "bill_date", "sort_dir": "desc", "limit": 5},
                              headers=h)
            assert r.status_code == 200, r.text
            dates = [row["bill_date"] for row in r.json()["rows"] if row["bill_date"]]
            assert dates == sorted(dates, reverse=True), dates
    asyncio.run(_run())


def test_pagination_offset_changes_rows():
    async def _run():
        async with httpx.AsyncClient(timeout=60.0) as cli:
            h = {"Authorization": f"Bearer {await _token(cli)}"}
            p1 = (await cli.get(f"{BASE}/shopper-report/bills",
                                params={"limit": 5, "offset": 0}, headers=h)).json()
            p2 = (await cli.get(f"{BASE}/shopper-report/bills",
                                params={"limit": 5, "offset": 5}, headers=h)).json()
            if p1["total"] and p1["total"] > 10:
                b1 = {r["bill_number"] for r in p1["rows"]}
                b2 = {r["bill_number"] for r in p2["rows"]}
                assert b1 != b2, "offset did not advance the page"
    asyncio.run(_run())


def test_recency_path_scale_safe():
    """Recency filter returns a page (has_more flag) and intentionally omits the
    exact total — it must not 500."""
    async def _run():
        async with httpx.AsyncClient(timeout=90.0) as cli:
            h = {"Authorization": f"Bearer {await _token(cli)}"}
            r = await cli.get(f"{BASE}/shopper-report/bills",
                              params={"recency": "active", "limit": 5}, headers=h)
            assert r.status_code in (200, 400), r.text
            if r.status_code == 200:
                d = r.json()
                assert d["total"] is None
                assert "has_more" in d
                for row in d["rows"]:
                    assert row["recency"].startswith("Active")
    asyncio.run(_run())


def test_filter_options():
    async def _run():
        async with httpx.AsyncClient(timeout=30.0) as cli:
            h = {"Authorization": f"Bearer {await _token(cli)}"}
            r = await cli.get(f"{BASE}/shopper-report/filter-options", headers=h)
            assert r.status_code == 200, r.text
            d = r.json()
            assert isinstance(d["stores"], list)
            assert isinstance(d["zones"], list)
    asyncio.run(_run())


def test_csv_export_header_and_rows():
    async def _run():
        async with httpx.AsyncClient(timeout=90.0) as cli:
            h = {"Authorization": f"Bearer {await _token(cli)}"}
            r = await cli.get(f"{BASE}/shopper-report/export",
                              params={"bill_type": "return"}, headers=h)
            assert r.status_code == 200, r.text
            assert "text/csv" in r.headers.get("content-type", "")
            reader = csv.reader(io.StringIO(r.text))
            rows = list(reader)
            assert len(rows[0]) == len(EXPECTED_KEYS), rows[0]
            assert rows[0][0] == "Bill Date"
    asyncio.run(_run())
