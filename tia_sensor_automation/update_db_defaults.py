"""
update_db_defaults.py — Update GlobalDB array default values from Excel.

Workflow
--------
  1. Read db_defaults.xlsx (DB_Name, Array_Name, Array_Index, Variable_Name, Default_Value).
  2. Group rows by DB_Name.
  3. Connect to running TIA Portal V19 instance.
  4. For each unique DB:
       a. Export DB as SimaticML XML.
       b. Patch <StartValue> elements in the XML.
       c. Delete the existing DB and reimport the modified XML.
  5. Compile and save.

Run as Administrator — required by the TIA Portal Openness API.
"""

import sys
import textwrap
import time
from collections import defaultdict

from db_xml_updater import update_db_defaults as patch_xml
from excel_reader import read_db_default_rows
from tia_portal import TIASession


def _banner() -> None:
    print("=" * 60)
    print("  TIA Portal V19 — DB Default Value Updater")
    print("  Run as Administrator  |  TIA Portal must be open")
    print("=" * 60)


def _step(n: int | str, title: str) -> None:
    print(f"\n[Step {n}] {title}")
    print("-" * 50)


def _group_by_db(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["db_name"]].append(row)
    return dict(groups)


def main() -> int:
    _banner()
    t_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Step 1 — Read Excel
    # ------------------------------------------------------------------
    _step(1, "Reading DB default-value rows from db_defaults.xlsx")
    try:
        rows = read_db_default_rows()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 1

    if not rows:
        print("  No rows found — nothing to do.")
        return 0

    groups = _group_by_db(rows)
    print(f"  Rows loaded : {len(rows)}")
    print(f"  Unique DBs  : {len(groups)}")
    for db_name, db_rows in groups.items():
        print(f"    '{db_name}' — {len(db_rows)} update(s)")

    # ------------------------------------------------------------------
    # Steps 2-5 inside TIASession
    # ------------------------------------------------------------------
    try:
        with TIASession() as session:

            _step(2, "Attached to TIA Portal V19")

            _step(3, "Compiling (ensures DBs are consistent before export)")
            session.compile()

            total_updated = 0

            for db_name, db_rows in groups.items():
                _step(f"4/{db_name}", f"Processing '{db_name}'")

                xml_path = session.export_db(db_name)

                updated = patch_xml(xml_path, db_rows)
                print(f"  → {updated} value(s) updated in XML")
                total_updated += updated

                session.import_db(xml_path, db_name)

            _step(5, "Final compile")
            result = session.compile()
            if result.ErrorCount > 0:
                print(f"  WARNING: {result.ErrorCount} compile error(s) — review messages above.")

            _step(6, "Saving project")  # triggered by TIASession.__exit__

    except RuntimeError as exc:
        print(f"\n  RUNTIME ERROR:\n{textwrap.indent(str(exc), '    ')}")
        return 1
    except ValueError as exc:
        print(f"\n  CONFIGURATION ERROR:\n{textwrap.indent(str(exc), '    ')}")
        return 1
    except Exception as exc:
        print(f"\n  UNEXPECTED ERROR: {type(exc).__name__}: {exc}")
        raise

    elapsed = time.perf_counter() - t_start
    print(f"\n{'=' * 60}")
    print(f"  Done.  {len(rows)} row(s) | {len(groups)} DB(s) | {total_updated} value(s) updated  [{elapsed:.1f}s]")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
