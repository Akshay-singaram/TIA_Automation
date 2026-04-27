"""
TIASession — context manager that wraps the TIA Portal V19 Openness API.

Uses pythonnet (clr) to load Siemens.Engineering.dll and call .NET methods
directly from Python.  Must be run as Administrator.
"""

import os
import sys

from config import (
    BLOCK_GROUP_PATH,
    EXPORT_DIR,
    SOURCE_FB_NAME,
    TARGET_FC_NAME,
    TIA_DLL_PATH,
)


def _bootstrap_clr() -> None:
    """Add the DLL directory to sys.path and load Siemens.Engineering."""
    import clr  # pythonnet

    dll_dir = os.path.dirname(TIA_DLL_PATH)
    if dll_dir not in sys.path:
        sys.path.insert(0, dll_dir)

    clr.AddReference("System")
    clr.AddReference(TIA_DLL_PATH)


class TIASession:
    """
    Context manager for TIA Portal V19 Openness API operations.

    Usage
    -----
    with TIASession() as session:
        session.create_instance_db("Sensor1")
        path = session.export_fc()
        # … modify path …
        session.import_fc(path)
        session.compile()
    # project is saved automatically on clean exit
    """

    def __init__(self, device_name: str = None) -> None:
        # Optional: restrict to a specific PLC device by name
        self.device_name = device_name

        self._portal = None
        self._project = None
        self._plc_software = None
        self._block_group = None
        self._fc_export_group = None   # group where the target FC lives

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "TIASession":
        _bootstrap_clr()

        import Siemens.Engineering as eng

        # Attach to the first running TIA Portal V19 process
        processes = list(eng.TiaPortal.GetProcesses())
        if not processes:
            raise RuntimeError(
                "No running TIA Portal V19 instance found.\n"
                "  → Open TIA Portal V19 with your project before running this script.\n"
                "  → Run this script as Administrator."
            )
        print(f"  [TIA] Found {len(processes)} TIA Portal process(es) — attaching to first.")
        self._portal = processes[0].Attach()

        projects = list(self._portal.Projects)
        if not projects:
            raise RuntimeError(
                "No project is open in TIA Portal. "
                "Open the target project first."
            )
        self._project = projects[0]
        print(f"  [TIA] Project : {self._project.Name}")

        self._plc_software = self._find_plc_software(None)
        self._block_group = self._resolve_block_group(BLOCK_GROUP_PATH)

        os.makedirs(EXPORT_DIR, exist_ok=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None and self._project is not None:
            try:
                print("  [TIA] Saving project…")
                self._project.Save()
                print("  [TIA] Project saved successfully.")
            except Exception as exc:
                print(f"  [TIA] WARNING — could not save project: {exc}")
        return False  # never suppress exceptions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_software_container_type():
        """
        Locate the SoftwareContainer .NET type through reflection.

        The namespace changed between TIA Portal versions:
          V15–V18  →  Siemens.Engineering.HW.Features.SoftwareContainer
          V19+     →  Siemens.Engineering.HW.Features.SoftwareContainer  (same)
        Using reflection avoids hard-coding the import path and works even if
        pythonnet cannot resolve a deep sub-namespace via `import`.
        """
        from System import AppDomain

        candidates = [
            "Siemens.Engineering.HW.Features.SoftwareContainer",
            "Siemens.Engineering.HW.Software.SoftwareContainer",
            "Siemens.Engineering.SW.SoftwareContainer",
        ]
        for asm in AppDomain.CurrentDomain.GetAssemblies():
            if "Siemens.Engineering" not in str(asm.FullName):
                continue
            for name in candidates:
                t = asm.GetType(name)
                if t is not None:
                    print(f"  [TIA] SoftwareContainer type: {name}")
                    return t

        raise RuntimeError(
            "Cannot locate SoftwareContainer in the loaded Siemens.Engineering assembly.\n"
            "  Verify TIA_DLL_PATH in config.py points to the correct V19 DLL."
        )

    def _find_plc_software(self, _unused):
        """Walk all devices recursively and return the first PLC software container."""
        sc_type = self._get_software_container_type()

        devices = list(self._project.Devices)
        print(f"  [TIA] Devices in project: {[d.Name for d in devices]}")

        for device in devices:
            if self.device_name and device.Name != self.device_name:
                continue
            result = self._scan_device_items(device.DeviceItems, sc_type, device.Name)
            if result is not None:
                return result

        raise RuntimeError(
            "Could not find a PLC software container in the open project.\n"
            f"  device_name filter = {self.device_name!r}\n"
            "  Ensure a PLC device is present and configured."
        )

    def _scan_device_items(self, items, sc_type, device_name: str):
        """Recursively search DeviceItems for a SoftwareContainer with a BlockGroup."""
        for item in items:
            try:
                container = item.GetService[sc_type]()
                if container is not None:
                    software = container.Software
                    if hasattr(software, "BlockGroup"):
                        print(
                            f"  [TIA] PLC software found on device '{device_name}'"
                            f", item '{item.Name}'."
                        )
                        return software
            except Exception:
                pass
            # Recurse into nested DeviceItems (rack slots, sub-modules, etc.)
            try:
                result = self._scan_device_items(item.DeviceItems, sc_type, device_name)
                if result is not None:
                    return result
            except Exception:
                pass
        return None

    def _resolve_block_group(self, path: str):
        """
        Navigate a '/'-delimited sub-group path starting from the root
        BlockGroup ("Program blocks").

        An empty path returns the root BlockGroup itself.
        """
        group = self._plc_software.BlockGroup
        if not path or not path.strip():
            return group

        for part in path.split("/"):
            part = part.strip()
            if not part:
                continue
            child = group.Groups.Find(part)
            if child is None:
                available = [g.Name for g in group.Groups]
                raise ValueError(
                    f"Block group '{part}' not found under '{group.Name}'.\n"
                    f"  Available sub-groups: {available}\n"
                    f"  Check BLOCK_GROUP_PATH in config.py."
                )
            group = child
        return group

    def _find_block_recursive(self, group, name: str):
        """
        Depth-first search for a block by name across *group* and all
        its sub-groups.  Returns (block, parent_group) or (None, None).
        """
        found = group.Blocks.Find(name)
        if found is not None:
            return found, group
        for sub in group.Groups:
            result, parent = self._find_block_recursive(sub, name)
            if result is not None:
                return result, parent
        return None, None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_instance_db(self, sensor_name: str, source_fb_name: str = None) -> tuple[str, bool]:
        """
        Create a global instance DB named ``{sensor_name}_DB`` that
        instantiates *source_fb_name*.

        Skips creation (logs a message) if the DB already exists.
        Returns ``(db_name, was_created)``.
        """
        fb_name = source_fb_name or SOURCE_FB_NAME
        db_name = f"{sensor_name}_DB"

        existing = self._block_group.Blocks.Find(db_name)
        if existing is not None:
            print(f"    [DB] '{db_name}' already exists — skipping.")
            return db_name, False

        fb_block, _ = self._find_block_recursive(self._plc_software.BlockGroup, fb_name)
        if fb_block is None:
            raise ValueError(
                f"Source FB '{fb_name}' not found in the project.\n"
                f"  Check SOURCE_FB_NAME in config.py."
            )

        # auto_number=True, number=1 (ignored when auto_number is True)
        self._block_group.Blocks.CreateInstanceDB(db_name, True, 1, fb_block)
        print(f"    [DB] Created '{db_name}'.")
        return db_name, True

    def export_fc(self, fc_name: str = None) -> str:
        """
        Export the target LAD FC as a SimaticML XML file.

        Stores the FC's parent group so ``import_fc`` can reimport to the
        correct location.  Returns the path to the exported file.
        """
        import Siemens.Engineering as eng
        from System.IO import FileInfo

        name = fc_name or TARGET_FC_NAME
        fc_block, parent_group = self._find_block_recursive(
            self._plc_software.BlockGroup, name
        )
        if fc_block is None:
            raise ValueError(
                f"Target FC '{name}' not found in the project.\n"
                f"  Check TARGET_FC_NAME in config.py."
            )
        self._fc_export_group = parent_group

        export_path = os.path.join(EXPORT_DIR, f"{name}.xml")
        fc_block.Export(FileInfo(export_path), eng.ExportOptions(0))
        print(f"  [FC]  Exported '{name}' → {export_path}")
        return export_path

    def import_fc(self, xml_path: str, fc_name: str = None) -> None:
        """
        Reimport a (modified) FC XML, overriding the existing block.

        Uses the parent group recorded during ``export_fc``; falls back to
        the configured block group.
        """
        import Siemens.Engineering as eng
        from System.IO import FileInfo

        name = fc_name or TARGET_FC_NAME
        group = self._fc_export_group or self._block_group
        group.Blocks.Import(FileInfo(xml_path), eng.ImportOptions.Override)
        print(f"  [FC]  Reimported '{name}' from {xml_path}")

    def compile(self):
        """
        Compile the PLC software and print all compiler messages.
        Returns the raw CompilerResult object.
        """
        import Siemens.Engineering.Compiler as compiler_ns

        compilable = self._plc_software.GetService[compiler_ns.ICompilable]()
        if compilable is None:
            raise RuntimeError("PLC software does not expose ICompilable — cannot compile.")

        result = compilable.Compile()
        print(
            f"  [Compile] Result: {result.State}  "
            f"(errors={result.ErrorCount}, warnings={result.WarningCount})"
        )
        for msg in result.Messages:
            level = getattr(msg, "WarningLevel", "?")
            path = getattr(msg, "PathName", "")
            desc = getattr(msg, "Description", str(msg))
            print(f"    [{level}] {path}: {desc}")
        return result
