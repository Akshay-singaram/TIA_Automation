"""
TIASession — context manager that wraps the TIA Portal V19 Openness API.

Uses pythonnet (clr) to load Siemens.Engineering.dll and call .NET methods
directly from Python.  Must be run as Administrator.
"""

import os
import sys

from config import EXPORT_DIR, TIA_DLL_PATH


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
        group = session.get_block_group("Sensors")
        session.create_instance_db("Sensor1", "Source_FB", group)
        path = session.export_fc("Main_FC")
        # … modify path …
        session.import_fc(path, "Main_FC")
        session.compile()
    # project is saved automatically on clean exit
    """

    def __init__(self, device_name: str | None = None) -> None:
        self.device_name = device_name
        self._portal = None
        self._project = None
        self._plc_software = None
        self._group_cache: dict = {}       # path str → resolved .NET group object
        self._fc_export_groups: dict = {}  # fc_name → parent group used at export time

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "TIASession":
        _bootstrap_clr()

        import Siemens.Engineering as eng

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
            raise RuntimeError("No project is open in TIA Portal. Open the target project first.")
        self._project = projects[0]
        print(f"  [TIA] Project : {self._project.Name}")

        self._plc_software = self._find_plc_software()
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
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_software_container_type():
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

    def _find_plc_software(self):
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
        for item in items:
            try:
                container = item.GetService[sc_type]()
                if container is not None:
                    software = container.Software
                    if hasattr(software, "BlockGroup"):
                        print(f"  [TIA] PLC software found on device '{device_name}', item '{item.Name}'.")
                        return software
            except Exception:
                pass
            try:
                result = self._scan_device_items(item.DeviceItems, sc_type, device_name)
                if result is not None:
                    return result
            except Exception:
                pass
        return None

    def _resolve_block_group(self, path: str):
        """Navigate a '/'-delimited sub-group path from the root BlockGroup."""
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
                    f"  Available sub-groups: {available}"
                )
            group = child
        return group

    def _find_block_recursive(self, group, name: str):
        """DFS for a block by name. Returns (block, parent_group) or (None, None)."""
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

    def get_block_group(self, path: str):
        """
        Return the resolved .NET block group for *path*, using a cache so
        the same path is only navigated once per session.
        """
        if path not in self._group_cache:
            self._group_cache[path] = self._resolve_block_group(path)
        return self._group_cache[path]

    def create_instance_db(self, sensor_name: str, source_fb_name: str, block_group) -> tuple[str, bool]:
        """
        Create a global instance DB named ``{sensor_name}_DB`` in *block_group*
        instantiating *source_fb_name*.  Skips if DB already exists.
        Returns ``(db_name, was_created)``.
        """
        db_name = f"{sensor_name}_DB"

        existing = block_group.Blocks.Find(db_name)
        if existing is not None:
            print(f"    [DB] '{db_name}' already exists — skipping.")
            return db_name, False

        block_group.Blocks.CreateInstanceDB(db_name, True, 1, source_fb_name)
        print(f"    [DB] Created '{db_name}'.")
        return db_name, True

    def export_fc(self, fc_name: str) -> str:
        """
        Export the named LAD FC as SimaticML XML.
        Returns the path to the exported file.
        """
        import Siemens.Engineering as eng
        from System.IO import FileInfo

        fc_block, parent_group = self._find_block_recursive(self._plc_software.BlockGroup, fc_name)
        if fc_block is None:
            raise ValueError(f"Target FC '{fc_name}' not found in the project.")
        self._fc_export_groups[fc_name] = parent_group

        export_path = os.path.join(EXPORT_DIR, f"{fc_name}.xml")
        if os.path.exists(export_path):
            os.remove(export_path)
        fc_block.Export(FileInfo(export_path), eng.ExportOptions(0))
        print(f"  [FC]  Exported '{fc_name}' → {export_path}")
        return export_path

    def import_fc(self, xml_path: str, fc_name: str) -> None:
        """
        Delete the existing FC then reimport the modified XML as a fresh block.
        (TIA Portal requires CompileUnits to be empty before importing.)
        """
        import Siemens.Engineering as eng
        from System.IO import FileInfo

        fc_block, _ = self._find_block_recursive(self._plc_software.BlockGroup, fc_name)
        if fc_block is not None:
            fc_block.Delete()
            print(f"  [FC]  Deleted existing '{fc_name}' for clean reimport.")

        group = self._fc_export_groups.get(fc_name) or self._plc_software.BlockGroup
        group.Blocks.Import(FileInfo(xml_path), eng.ImportOptions.Override)
        print(f"  [FC]  Reimported '{fc_name}' from {xml_path}")

    def export_db(self, db_name: str) -> str:
        """
        Export the named GlobalDB as SimaticML XML.
        Returns the path to the exported file.

        If TIA Portal refuses to export because the block is inconsistent
        (e.g. a previous run imported bad values), the existing XML file
        from the last run is reused so the caller can patch and re-import
        to restore a consistent state.
        """
        import shutil
        import Siemens.Engineering as eng
        from System.IO import FileInfo

        db_block, parent_group = self._find_block_recursive(self._plc_software.BlockGroup, db_name)
        if db_block is None:
            raise ValueError(f"DB '{db_name}' not found in the project.")
        self._fc_export_groups[db_name] = parent_group

        export_path = os.path.join(EXPORT_DIR, f"{db_name}.xml")
        backup_path = export_path + ".bak"

        # Back up the existing file so we can restore it if export fails
        if os.path.exists(export_path):
            shutil.copy2(export_path, backup_path)
            os.remove(export_path)

        try:
            db_block.Export(FileInfo(export_path), eng.ExportOptions(0))
            print(f"  [DB]  Exported '{db_name}' → {export_path}")
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception as exc:
            if "Inconsistent" in str(exc) and os.path.exists(backup_path):
                shutil.move(backup_path, export_path)
                print(f"  [DB]  WARNING: '{db_name}' is inconsistent — reusing previous XML to self-heal.")
            else:
                if os.path.exists(backup_path):
                    shutil.move(backup_path, export_path)
                raise

        return export_path

    def import_db(self, xml_path: str, db_name: str) -> None:
        """
        Import the modified DB XML using Override (no delete).
        InstanceDBs do not have the IOrdered CompileUnit constraint that FCs have,
        so updating in-place via Override avoids the 'value cannot be changed'
        error that occurs when TIA Portal creates a fresh InstanceDB.
        """
        import Siemens.Engineering as eng
        from System.IO import FileInfo

        group = self._fc_export_groups.get(db_name) or self._plc_software.BlockGroup
        group.Blocks.Import(FileInfo(xml_path), eng.ImportOptions.Override)
        print(f"  [DB]  Updated '{db_name}' from {xml_path}")

    def compile(self):
        """Compile the PLC software and print all messages. Returns the CompilerResult."""
        import Siemens.Engineering.Compiler as compiler_ns

        compilable = self._plc_software.GetService[compiler_ns.ICompilable]()
        if compilable is None:
            raise RuntimeError("PLC software does not expose ICompilable — cannot compile.")

        result = compilable.Compile()
        print(f"  [Compile] Result: {result.State}  (errors={result.ErrorCount}, warnings={result.WarningCount})")
        for msg in result.Messages:
            level = getattr(msg, "WarningLevel", "?")
            path  = getattr(msg, "PathName", "")
            desc  = getattr(msg, "Description", str(msg))
            print(f"    [{level}] {path}: {desc}")
        return result
