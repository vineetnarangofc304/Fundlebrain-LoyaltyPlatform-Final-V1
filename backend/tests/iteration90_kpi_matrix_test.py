"""Iteration 90 - Store-wise KPI, Weekly KPI, CRM visit-account + POS hook.

Validates the client-requested reports and denormalisation:
- GET /api/kpi-reports/store-wise-kpi (rows, 41-col matrix, filters, sort)
- GET /api/kpi-reports/store-wise-kpi/export (CSV, all 41 columns)
- POST /api/exports/request store_wise_kpi (small dataset -> instant)
- GET /api/kpi-reports/weekly-kpi (granularity day/week/month, sort)
- POST /api/exports/request weekly_kpi
- GET /api/kpi-reports/crm-customers (new fields: total_purchase / first_visit_account / last_visit_account)
- GET /api/kpi-reports/crm-customers/export (CSV headers include the 3 new columns)
- GET /api/kpi-reports/crm-visit-accounts/audit
- POST /api/kpi-reports/crm-visit-accounts/backfill (scoped by mobile)
- POS bill hook: posAddPoint updates last_visit_account / first_visit_account /
  total_purchase without breaking points earning.
"""
import asyncio
import os
import uuid
import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

API = os.environ.get("API_URL") or "https://kazo-loyalty-ops.preview.emergentagent.com"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN = os.environ.get("DB_NAME", "kazo_fundle_db")
XKEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCH = "KAZO_FUNDLE"
STORE = "K00055"
CRM_EMAIL = "masteradmin@fundle.io"
CRM_PW = "Master@2026"

START = "2021-01-01"
END = "2026-12-31"


@pytest.mark.asyncio
async def _run():
    c = AsyncIOMotorClient(MONGO)
    db = c[DBN]
    failures = []

    def check(name, cond, extra=""):
        status = "PASS" if cond else "FAIL"
        print(f"{status} {name} {extra}")
        if not cond:
            failures.append(f"{name} :: {extra}")

    async with httpx.AsyncClient(timeout=180) as client:
        # ---- CRM login ----
        lr = await client.post(f"{API}/api/auth/login", json={"email": CRM_EMAIL, "password": CRM_PW})
        check("CRM login", lr.status_code == 200, str(lr.status_code))
        if lr.status_code != 200:
            pytest.fail("Cannot login: " + lr.text[:200])
        tok = lr.json().get("access_token") or lr.json().get("token")
        auth = {"Authorization": f"Bearer {tok}"}

        # ═══════════ 1) Store-wise KPI ═══════════
        r = await client.get(f"{API}/api/kpi-reports/store-wise-kpi",
                             params={"start_date": START, "end_date": END},
                             headers=auth)
        check("store-wise-kpi 200", r.status_code == 200, str(r.status_code)[:200])
        j = r.json() if r.status_code == 200 else {}
        rows = j.get("rows", [])
        cols = j.get("columns", [])
        check("store-wise-kpi has rows", len(rows) >= 1, f"count={len(rows)}")
        check("store-wise-kpi has 41 columns", len(cols) == 41, f"cols={len(cols)}")

        # column keys sanity: expected identifiers
        keys = {c.get("key") for c in cols}
        expected_keys = {"store_name", "email", "store_code", "store_class", "zone", "city",
                         "overall_sales", "total_discount", "fresh_bills", "fresh_value",
                         "fresh_discount", "return_bills", "return_value", "return_discount",
                         "new_fresh_txn", "new_return_txn", "new_fresh_value", "new_return_value",
                         "new_fresh_atv", "new_return_atv", "repeat_fresh_txn", "repeat_return_txn",
                         "repeat_fresh_value", "repeat_return_value", "repeat_fresh_atv",
                         "repeat_return_atv", "mapped_fresh_txn", "mapped_return_txn",
                         "mapped_fresh_value", "mapped_return_value", "mapped_fresh_atv",
                         "mapped_return_atv", "unmapped_fresh_txn", "unmapped_return_txn",
                         "unmapped_fresh_value", "unmapped_return_value", "unmapped_fresh_atv",
                         "unmapped_return_atv", "overall_customers", "new_customer_count",
                         "existing_customers"}
        missing = expected_keys - keys
        check("store-wise-kpi columns match spec", not missing, f"missing={missing}")

        # email synthesised = code + @KAZO.com
        if rows:
            r0 = rows[0]
            code0 = r0.get("store_code")
            email0 = r0.get("email")
            if code0 and code0 != "—":
                check("email = store_code@KAZO.com",
                      email0 == f"{code0}@KAZO.com", f"code={code0} email={email0}")

        # sorting
        r_asc = await client.get(f"{API}/api/kpi-reports/store-wise-kpi",
                                 params={"start_date": START, "end_date": END,
                                         "sort_by": "overall_sales", "sort_dir": "asc"},
                                 headers=auth)
        rows_asc = r_asc.json().get("rows", []) if r_asc.status_code == 200 else []
        if len(rows_asc) >= 2:
            check("store-wise-kpi sort asc",
                  rows_asc[0]["overall_sales"] <= rows_asc[-1]["overall_sales"],
                  f"first={rows_asc[0]['overall_sales']} last={rows_asc[-1]['overall_sales']}")

        r_desc = await client.get(f"{API}/api/kpi-reports/store-wise-kpi",
                                  params={"start_date": START, "end_date": END,
                                          "sort_by": "fresh_bills", "sort_dir": "desc"},
                                  headers=auth)
        rows_desc = r_desc.json().get("rows", []) if r_desc.status_code == 200 else []
        if len(rows_desc) >= 2:
            check("store-wise-kpi sort by fresh_bills desc",
                  rows_desc[0]["fresh_bills"] >= rows_desc[-1]["fresh_bills"],
                  f"first={rows_desc[0]['fresh_bills']} last={rows_desc[-1]['fresh_bills']}")

        # filter by a store_id from the rows
        if rows:
            sid = rows[0].get("store_id")
            if sid:
                rf = await client.get(f"{API}/api/kpi-reports/store-wise-kpi",
                                      params={"start_date": START, "end_date": END,
                                              "store_id": sid},
                                      headers=auth)
                rfj = rf.json() if rf.status_code == 200 else {}
                filt_rows = rfj.get("rows", [])
                check("filter by store_id returns <= all-rows",
                      len(filt_rows) <= len(rows) and len(filt_rows) >= 1,
                      f"filtered={len(filt_rows)} total={len(rows)}")

        # totals
        totals = j.get("totals") or {}
        check("store-wise-kpi has totals dict", isinstance(totals, dict) and "overall_sales" in totals,
              str(list(totals.keys())[:5]))

        # ═══════════ 2) Store-wise KPI export (POST /api/exports/request) ═══════════
        er = await client.post(f"{API}/api/exports/request",
                               json={"report_type": "store_wise_kpi",
                                     "params": {"start_date": START, "end_date": END},
                                     "known_total": len(rows)},
                               headers=auth)
        check("exports/request store_wise_kpi 200", er.status_code == 200, str(er.status_code)[:200])
        ej = er.json() if er.status_code == 200 else {}
        exp_id = ej.get("export_id")
        check("store_wise_kpi export instant ready",
              ej.get("mode") == "instant" and ej.get("status") == "ready",
              str(ej))
        if exp_id:
            dl = await client.get(f"{API}/api/exports/{exp_id}/download", headers=auth)
            check("store_wise_kpi download 200", dl.status_code == 200, str(dl.status_code))
            csv_text = dl.text
            header = csv_text.splitlines()[0] if csv_text else ""
            check("CSV header has Overall Sales", "Overall Sales" in header, header[:200])
            check("CSV header has New Customer ATV (Fresh)",
                  "New Customer ATV (Fresh)" in header, header[:200])
            # 41 columns => 40 commas at minimum (some labels contain commas? No they don't)
            n_cols = header.count(",") + 1 if header else 0
            check("CSV has 41 columns", n_cols == 41, f"n_cols={n_cols}")

        # ═══════════ 3) Weekly KPI ═══════════
        for gran in ("day", "week", "month"):
            rw = await client.get(f"{API}/api/kpi-reports/weekly-kpi",
                                  params={"start_date": START, "end_date": END,
                                          "granularity": gran},
                                  headers=auth)
            check(f"weekly-kpi {gran} 200", rw.status_code == 200, str(rw.status_code)[:120])
            jw = rw.json() if rw.status_code == 200 else {}
            check(f"weekly-kpi {gran} rows>=1", len(jw.get("rows", [])) >= 1,
                  f"count={len(jw.get('rows', []))}")
            check(f"weekly-kpi {gran} granularity echoed",
                  jw.get("granularity") == gran, str(jw.get("granularity")))
            cols_w = jw.get("columns", [])
            check(f"weekly-kpi {gran} columns >=26",
                  len(cols_w) >= 26, f"cols={len(cols_w)}")
            # period label pattern
            rowsw = jw.get("rows", [])
            if rowsw:
                p0 = rowsw[0].get("period") or ""
                if gran == "month":
                    check("weekly-kpi month period YYYY-MM",
                          len(p0) == 7 and p0[4] == "-", p0)
                elif gran == "day":
                    check("weekly-kpi day period YYYY-MM-DD",
                          len(p0) == 10, p0)
                elif gran == "week":
                    check("weekly-kpi week period YYYY-Wxx", "W" in p0, p0)

        # sort_by=period desc
        rwd = await client.get(f"{API}/api/kpi-reports/weekly-kpi",
                               params={"start_date": START, "end_date": END,
                                       "granularity": "month",
                                       "sort_by": "period", "sort_dir": "desc"},
                               headers=auth)
        if rwd.status_code == 200:
            rowsd = rwd.json().get("rows", [])
            if len(rowsd) >= 2:
                check("weekly-kpi period desc sort",
                      rowsd[0]["period"] >= rowsd[-1]["period"],
                      f"{rowsd[0]['period']} vs {rowsd[-1]['period']}")

        # weekly export
        wr = await client.post(f"{API}/api/exports/request",
                               json={"report_type": "weekly_kpi",
                                     "params": {"start_date": START, "end_date": END,
                                                "granularity": "month"},
                                     "known_total": 50},
                               headers=auth)
        check("exports/request weekly_kpi 200", wr.status_code == 200, str(wr.status_code)[:200])
        wj = wr.json() if wr.status_code == 200 else {}
        check("weekly_kpi export instant ready",
              wj.get("mode") == "instant" and wj.get("status") == "ready", str(wj))
        wid = wj.get("export_id")
        if wid:
            wdl = await client.get(f"{API}/api/exports/{wid}/download", headers=auth)
            check("weekly_kpi download 200", wdl.status_code == 200, str(wdl.status_code))
            wh = wdl.text.splitlines()[0] if wdl.text else ""
            check("weekly CSV has Period + Data Collection",
                  "Period" in wh and "Data Collection" in wh, wh[:250])

        # ═══════════ 4) CRM-customer report new fields ═══════════
        crm = await client.get(f"{API}/api/kpi-reports/crm-customers",
                               params={"page": 1, "page_size": 25,
                                       "sort_by": "total_purchase", "sort_dir": "desc"},
                               headers=auth)
        check("crm-customers 200", crm.status_code == 200, str(crm.status_code)[:200])
        cj = crm.json() if crm.status_code == 200 else {}
        crows = cj.get("rows", []) or cj.get("customers", []) or []
        check("crm-customers returned rows", len(crows) >= 1, f"n={len(crows)}")
        if crows:
            keys0 = set(crows[0].keys())
            for f in ("total_purchase", "first_visit_account", "last_visit_account"):
                check(f"crm-customers row has {f}", f in keys0, str(list(keys0)[:12]))
            # sort desc: total_purchase non-increasing
            vals = [float(r.get("total_purchase") or 0) for r in crows]
            check("crm-customers sort by total_purchase desc",
                  all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)),
                  f"vals[:5]={vals[:5]}")
            # at least one has non-empty visit accounts (dataset has ~28)
            non_empty = sum(1 for r in crows if r.get("first_visit_account"))
            check("crm-customers has customers with first_visit_account set (top page)",
                  non_empty >= 1, f"non_empty={non_empty}")

        # CRM export headers
        crx = await client.get(f"{API}/api/kpi-reports/crm-customers/export",
                               headers=auth,
                               params={"page_size": 50})
        check("crm-customers export 200", crx.status_code == 200, str(crx.status_code)[:200])
        if crx.status_code == 200:
            head = (crx.text.splitlines() or [""])[0]
            for lbl in ("Total Purchase (incl. Tax)", "First Visit Account", "Last Visit Account"):
                check(f"CRM CSV header has '{lbl}'", lbl in head, head[:300])

        # ═══════════ 5) Visit accounts audit + backfill ═══════════
        aud = await client.get(f"{API}/api/kpi-reports/crm-visit-accounts/audit", headers=auth)
        check("crm-visit-accounts/audit 200", aud.status_code == 200, str(aud.status_code))
        aj = aud.json() if aud.status_code == 200 else {}
        check("audit returns total_customers",
              isinstance(aj.get("total_customers"), int) and aj["total_customers"] > 0,
              str(aj))
        check("audit returns missing_visit_accounts",
              isinstance(aj.get("missing_visit_accounts"), int), str(aj))

        # scoped backfill (empty body -> full backfill; use one mobile only to be fast)
        # pick an existing transaction mobile
        one = await db.transactions.find_one({"customer_mobile": {"$nin": [None, ""]}},
                                             {"customer_mobile": 1, "store_code": 1,
                                              "store_name": 1, "net_amount": 1})
        if one and one.get("customer_mobile"):
            m = one["customer_mobile"]
            bf = await client.post(
                f"{API}/api/kpi-reports/crm-visit-accounts/backfill",
                json={"mobile": m}, headers=auth)
            check("backfill scoped 200", bf.status_code == 200, str(bf.status_code)[:200])
            bj = bf.json() if bf.status_code == 200 else {}
            check("backfill ok=True", bj.get("ok") is True, str(bj))
            check("backfill mobiles_scanned>=1",
                  (bj.get("mobiles_scanned") or 0) >= 1, str(bj))
            # verify customer row now has the three fields
            cust = await db.customers.find_one({"mobile": m})
            if cust:
                check("customer has first_visit_account after backfill",
                      bool(cust.get("first_visit_account")),
                      str(cust.get("first_visit_account")))
                check("customer has last_visit_account after backfill",
                      bool(cust.get("last_visit_account")),
                      str(cust.get("last_visit_account")))
                check("customer has total_purchase after backfill",
                      isinstance(cust.get("total_purchase"), (int, float)),
                      str(cust.get("total_purchase")))
                # format contains ' · ' when both code+name
                fva = cust.get("first_visit_account") or ""
                if "·" in fva:
                    check("visit account format CODE · NAME",
                          fva.count("·") == 1 and " · " in fva, fva)

        # ═══════════ 6) POS posAddPoint hook: last/first visit + total_purchase ═══════════
        # digits-only mobile that starts with 6-9 (Indian mobile validation)
        import random
        test_mobile = "99900" + "".join(str(random.randint(0, 9)) for _ in range(5))
        # ensure clean
        await db.customers.delete_many({"mobile": test_mobile})
        await db.transactions.delete_many({"customer_mobile": test_mobile})
        await db.points_ledger.delete_many({"customer_mobile": test_mobile})

        hdr = {"x-api-key": XKEY, "Content-Type": "application/json"}
        bill1 = "ITER90A-" + uuid.uuid4().hex[:6]
        addp1 = await client.post(
            f"{API}/api/pos/posAddPoint",
            json={
                "merchant_id": MERCH, "customer_key": STORE,
                "customer": {"mobile": test_mobile, "name": "Iter90 Hook Test"},
                "transaction": {"number": bill1, "amount": "2500"},
            }, headers=hdr,
        )
        check("posAddPoint bill1 200", addp1.status_code == 200, str(addp1.status_code)[:180])
        await asyncio.sleep(1.2)

        cust = await db.customers.find_one({"mobile": test_mobile})
        check("hook: customer created", bool(cust))
        if cust:
            check("hook: last_visit_account set",
                  bool(cust.get("last_visit_account")),
                  str(cust.get("last_visit_account")))
            check("hook: first_visit_account set on new customer",
                  bool(cust.get("first_visit_account")),
                  str(cust.get("first_visit_account")))
            check("hook: total_purchase increased to ~2500",
                  abs(float(cust.get("total_purchase") or 0) - 2500) < 0.5,
                  str(cust.get("total_purchase")))
            check("hook: points_balance earned (non-zero)",
                  int(cust.get("points_balance") or 0) > 0,
                  str(cust.get("points_balance")))
            first_before = cust.get("first_visit_account")

            # second bill from a different store (use K00055 name resolution stays)
            bill2 = "ITER90B-" + uuid.uuid4().hex[:6]
            addp2 = await client.post(
                f"{API}/api/pos/posAddPoint",
                json={
                    "merchant_id": MERCH, "customer_key": STORE,
                    "customer": {"mobile": test_mobile, "name": "Iter90 Hook Test"},
                    "transaction": {"number": bill2, "amount": "1000"},
                }, headers=hdr,
            )
            check("posAddPoint bill2 200", addp2.status_code == 200, str(addp2.status_code)[:180])
            await asyncio.sleep(1.2)
            cust2 = await db.customers.find_one({"mobile": test_mobile})
            check("hook: total_purchase incremented to ~3500",
                  abs(float(cust2.get("total_purchase") or 0) - 3500) < 0.5,
                  str(cust2.get("total_purchase")))
            check("hook: first_visit_account unchanged after 2nd bill",
                  cust2.get("first_visit_account") == first_before,
                  f"before={first_before} now={cust2.get('first_visit_account')}")

        # cleanup
        await db.customers.delete_many({"mobile": test_mobile})
        await db.transactions.delete_many({"customer_mobile": test_mobile})
        await db.points_ledger.delete_many({"customer_mobile": test_mobile})

    c.close()

    if failures:
        pytest.fail("Failures:\n" + "\n".join(failures))


def test_iteration90_kpi_matrix():
    asyncio.run(_run())


if __name__ == "__main__":
    asyncio.run(_run())
