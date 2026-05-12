"""
Quick utility — exports one DB as-is and prints the path.
Run as Administrator with TIA Portal open.
Usage: python export_db_only.py <DB_Name>
"""

import sys
from tia_portal import TIASession

if len(sys.argv) < 2:
    print("Usage: python export_db_only.py <DB_Name>")
    print("Example: python export_db_only.py TI-10331-TI_DB")
    sys.exit(1)

db_name = sys.argv[1]

with TIASession() as session:
    print("Compiling first...")
    session.compile()
    path = session.export_db(db_name)
    print(f"\nExported to: {path}")
    print("Open that file to see the XML format TIA Portal uses.")
