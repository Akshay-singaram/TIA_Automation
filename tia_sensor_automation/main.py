"""
main.py — TIA Portal sensor automation entry point.

Workflow
--------
  1. Read sensor names from Excel.
  2. Connect to running TIA Portal V19 instance.
  3. Create one global instance DB per sensor (skip duplicates).
  4. Export target LAD FC as SimaticML XML.
  5. Inject one LAD network per sensor into the XML.
  6. Reimport the modified FC and compile.
  7. Save project (automatic on clean exit).

Run as Administrator — required by the TIA Portal Openness API.
"""

import sys
import textwrap
import time

from config import SOURCE_FB_NAME, TARGET_FC_NAME
from excel_reader import read_sensor_names
from network_xml_builder import inject_networks
from tia_portal import TIASession


def _banner() -> None:
    print("=" * 60)
    print("  TIA Portal V19 Sensor Automation")
    print("  Run as Administrator  |  TIA Portal must be open")
    print("=" * 60)


def _step(n: int, title: str) -> None:
    print(f"\n[Step {n}] {title}")
    print("-" * 50)


def main() -> int:
    _banner()
    t_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Step 1 — Read sensor list
    # ------------------------------------------------------------------
    _step(1, "Reading sensor names from Excel")
    try:
        sensors = read_sensor_names()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 1

    if not sensors:
        print("  No sensor names found — nothing to do.")
        return 0

    print(f"  Sensors found ({len(sensors)}): {', '.join(sensors)}")

    # ------------------------------------------------------------------
    # Steps 2-7 inside TIASession context manager
    # ------------------------------------------------------------------
    try:
        with TIASession() as session:

            # Step 2 confirmation (attach happens in __enter__)
            _step(2, "Attached to TIA Portal V19")

            # ----------------------------------------------------------
            # Step 3 — Create instance DBs
            # ----------------------------------------------------------
            _step(3, f"Creating instance DBs  (source FB: '{SOURCE_FB_NAME}')")
            created = skipped = 0
            for sensor in sensors:
                _, was_created = session.create_instance_db(sensor, SOURCE_FB_NAME)
                if was_created:
                    created += 1
                else:
                    skipped += 1
            print(f"  → Created: {created}   Skipped (already exist): {skipped}")

            # ----------------------------------------------------------
            # Step 4 — Export target FC
            # ----------------------------------------------------------
            _step(4, f"Exporting FC  '{TARGET_FC_NAME}'")
            xml_path = session.export_fc(TARGET_FC_NAME)

            # ----------------------------------------------------------
            # Step 5 — Inject LAD networks
            # ----------------------------------------------------------
            _step(5, "Injecting LAD networks into exported FC XML")
            injected = inject_networks(xml_path, sensors, SOURCE_FB_NAME)
            print(f"  → {injected} network(s) injected into {xml_path}")

            # ----------------------------------------------------------
            # Step 6 — Reimport and compile
            # ----------------------------------------------------------
            _step(6, "Reimporting modified FC and compiling")
            session.import_fc(xml_path, TARGET_FC_NAME)
            result = session.compile()
            if result.ErrorCount > 0:
                print(
                    f"  WARNING: Compilation finished with {result.ErrorCount} error(s). "
                    "Review messages above."
                )

            # Step 7 — Save is triggered by TIASession.__exit__
            _step(7, "Saving project")

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
    print(f"  Done.  {len(sensors)} sensor(s) processed in {elapsed:.1f}s.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
