"""
main.py — TIA Portal sensor/actuator automation entry point.

Workflow
--------
  1. Read rows from Excel (sensor name, source FB, target FC, block group).
  2. Connect to running TIA Portal V19 instance.
  3. For each unique (source FB / target FC / block group) group:
       a. Create one instance DB per sensor in that group.
  4. Compile (ensures all new DBs are consistent before export).
  5. For each group:
       a. Export the target FC as SimaticML XML.
       b. Inject one LAD network per sensor into the XML.
       c. Delete the existing FC and reimport the modified XML.
  6. Final compile and save.

Run as Administrator — required by the TIA Portal Openness API.
"""

import sys
import textwrap
import time
from collections import defaultdict

from excel_reader import read_sensor_rows
from network_xml_builder import inject_networks
from tia_portal import TIASession


def _banner() -> None:
    print("=" * 60)
    print("  TIA Portal V19 Sensor / Actuator Automation")
    print("  Run as Administrator  |  TIA Portal must be open")
    print("=" * 60)


def _step(n: int | str, title: str) -> None:
    print(f"\n[Step {n}] {title}")
    print("-" * 50)


def _group_rows(rows: list[dict]) -> dict[tuple, list[dict]]:
    """Group Excel rows by (source_fb, target_fc, block_group)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        key = (row["source_fb"], row["target_fc"], row["block_group"])
        groups[key].append(row)
    return dict(groups)


def main() -> int:
    _banner()
    t_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Step 1 — Read Excel
    # ------------------------------------------------------------------
    _step(1, "Reading sensor/actuator rows from Excel")
    try:
        rows = read_sensor_rows()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 1

    if not rows:
        print("  No rows found — nothing to do.")
        return 0

    groups = _group_rows(rows)
    print(f"  Rows loaded : {len(rows)}")
    print(f"  Groups (unique FB / FC / block-group combos): {len(groups)}")
    for (sfb, tfc, bg), grp_rows in groups.items():
        print(f"    Source FB='{sfb}'  Target FC='{tfc}'  Block Group='{bg}'  → {len(grp_rows)} sensor(s)")

    # ------------------------------------------------------------------
    # Steps 2-6 inside TIASession
    # ------------------------------------------------------------------
    try:
        with TIASession() as session:

            _step(2, "Attached to TIA Portal V19")

            # ----------------------------------------------------------
            # Step 3 — Create instance DBs for every group
            # ----------------------------------------------------------
            _step(3, "Creating instance DBs")
            total_created = total_skipped = 0

            for (source_fb, target_fc, block_group_path), grp_rows in groups.items():
                print(f"\n  Group: FB='{source_fb}'  FC='{target_fc}'  Group='{block_group_path}'")
                block_group = session.get_block_group(block_group_path)
                for row in grp_rows:
                    _, created = session.create_instance_db(row["sensor_name"], source_fb, block_group)
                    if created:
                        total_created += 1
                    else:
                        total_skipped += 1

            print(f"\n  → Created: {total_created}   Skipped (already exist): {total_skipped}")

            # ----------------------------------------------------------
            # Step 4 — Compile so all new DBs are consistent
            # ----------------------------------------------------------
            _step(4, "Compiling (ensures DBs are consistent before export)")
            session.compile()

            # ----------------------------------------------------------
            # Step 5 — Export → inject → reimport for every group
            # ----------------------------------------------------------
            _step(5, "Injecting networks and reimporting FCs")
            total_injected = 0

            for (source_fb, target_fc, block_group_path), grp_rows in groups.items():
                sensor_names = [r["sensor_name"] for r in grp_rows]
                print(f"\n  Group: FB='{source_fb}'  FC='{target_fc}'  ({len(sensor_names)} sensor(s))")

                xml_path = session.export_fc(target_fc)
                injected = inject_networks(xml_path, sensor_names, source_fb)
                print(f"  → {injected} network(s) injected")
                total_injected += injected

                session.import_fc(xml_path, target_fc)

            # ----------------------------------------------------------
            # Step 6 — Final compile
            # ----------------------------------------------------------
            _step(6, "Final compile")
            result = session.compile()
            if result.ErrorCount > 0:
                print(f"  WARNING: {result.ErrorCount} compile error(s) — review messages above.")

            _step(7, "Saving project")   # save triggered by TIASession.__exit__

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
    print(f"  Done.  {len(rows)} row(s) | {len(groups)} group(s) | {total_injected} network(s) injected  [{elapsed:.1f}s]")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
