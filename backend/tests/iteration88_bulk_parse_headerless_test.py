"""Iteration 88b — Bulk Bonus file parser must detect mobiles in HEADERLESS files and
ignore phantom empty rows (user file 'Kazo Bulk Points-4.xlsx' = one bare column of
10-digit mobiles, no header, ~999 trailing empty rows -> previously 'No mobiles detected')."""
import io
import csv
import openpyxl
from routes import mb_attachments as MBA


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r if isinstance(r, (list, tuple)) else [r])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


results = []
def check(name, cond, extra=""):
    results.append((name, cond))
    print(("PASS" if cond else "FAIL"), name, extra)


def main():
    # 1) headerless single-column xlsx + trailing empty rows (the user's exact shape)
    rows = [["8888888888"], ["9999999999"], ["8400010003"], ["9312359672"], ["9958447793"]]
    rows += [[None]] * 500  # phantom empties
    p = MBA._parse_xlsx(_xlsx(rows))
    m = MBA._detect_mobiles(p["columns"], p["rows"])
    check("headerless xlsx detects all 5 mobiles (empties ignored)", len(m) == 5, str(len(m)))
    check("first mobile (was header) not lost", "8888888888" in m, str(m[:2]))

    # 2) headerless CSV list of mobiles
    p2 = MBA._parse_csv(b"9958447793\n7652873375\n9356642237\n")
    m2 = MBA._detect_mobiles(p2["columns"], p2["rows"])
    check("headerless csv detects 3 mobiles", len(m2) == 3, str(m2))

    # 3) REGRESSION: normal headered CSV with points, duplicate summed
    p3 = MBA._parse_csv(b"Mobile,Points\n9312359672,100\n8018442341,250\n9312359672,50\n")
    m3 = MBA._detect_mobiles(p3["columns"], p3["rows"])
    mp3, dup3 = MBA._detect_points_pairs(p3["columns"], p3["rows"])
    check("headered csv keeps header", p3["columns"] == ["Mobile", "Points"], str(p3["columns"]))
    check("headered csv detects 2 unique mobiles", len(m3) == 2, str(m3))
    check("headered csv sums duplicate points (150)",
          any(x["mobile"] == "9312359672" and x["points"] == 150 for x in mp3), str(mp3))

    # 4) REGRESSION: headered xlsx with a MOBILE hint column mixed with an id column
    p4 = MBA._parse_xlsx(_xlsx([["CustomerID", "Mobile"], [1001, "9811696909"], [1002, "8018442341"]]))
    m4 = MBA._detect_mobiles(p4["columns"], p4["rows"])
    check("headered xlsx picks the mobile column not the id", set(m4) == {"9811696909", "8018442341"}, str(m4))

    npass = sum(1 for _, ok in results if ok)
    print(f"\n==== {npass}/{len(results)} PASS ====")
    return npass == len(results)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
