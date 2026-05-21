"""
Quick utility — exports one FB/FC as-is and prints the path.
Run as Administrator with TIA Portal open.
Usage: python export_fb_only.py <Block_Name>
Example: python export_fb_only.py Cause_n_Effect
"""

import os
import sys

import Siemens.Engineering as eng
from System.IO import FileInfo

from config import EXPORT_DIR
from tia_portal import TIASession

if len(sys.argv) < 2:
    print("Usage: python export_fb_only.py <Block_Name>")
    print("Example: python export_fb_only.py Cause_n_Effect")
    sys.exit(1)

block_name = sys.argv[1]

with TIASession() as session:
    block, _ = session._find_block_recursive(session._plc_software.BlockGroup, block_name)
    if block is None:
        print(f"ERROR: Block '{block_name}' not found in the project.")
        sys.exit(1)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    export_path = os.path.join(EXPORT_DIR, f"{block_name}.xml")
    if os.path.exists(export_path):
        os.remove(export_path)

    block.Export(FileInfo(export_path), eng.ExportOptions(0))
    print(f"\nExported to: {export_path}")
    print("Open that file to inspect the variable declarations and network XML structure.")
