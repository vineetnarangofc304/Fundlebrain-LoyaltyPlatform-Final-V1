"""Iteration 46 — ensure_indexes() must create all hot-path dashboard indexes.

Run: python backend/tests/iteration46_indexes_test.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from server import ensure_indexes
    from database import customers_col, transactions_col, points_ledger_col

    await ensure_indexes()

    cust = set((await customers_col.index_information()).keys())
    txn = set((await transactions_col.index_information()).keys())
    pl = set((await points_ledger_col.index_information()).keys())

    expect_cust = {"ix_cust_tier", "ix_cust_home_store", "ix_cust_last_visit",
                   "ix_cust_first_purchase", "ix_cust_lifetime_spend", "ix_cust_city",
                   "ix_cust_created", "ix_cust_visit_count"}
    expect_txn = {"ix_txn_store_billdate", "ix_txn_mobile_billdate", "ix_txn_is_return"}
    expect_pl = {"ix_pl_mobile", "ix_pl_type_expiry", "ix_pl_created", "ix_pl_bill"}
    # mobile equality index present under one of two names
    assert ("uniq_customer_mobile" in cust) or ("ix_cust_mobile" in cust), "no mobile index"

    missing_c = expect_cust - cust
    missing_t = expect_txn - txn
    missing_p = expect_pl - pl
    assert not missing_c, f"missing customer indexes: {missing_c}"
    assert not missing_t, f"missing txn indexes: {missing_t}"
    assert not missing_p, f"missing ledger indexes: {missing_p}"

    print("✅ PASS — all hot-path indexes present.")
    print("   customers:", sorted(cust))
    print("   transactions:", sorted(txn))
    print("   points_ledger:", sorted(pl))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print("❌ FAIL:", e)
        sys.exit(1)
