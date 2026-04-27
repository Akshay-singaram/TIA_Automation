# tia_sensor_automation

Automates repetitive TIA Portal V19 programming for large sensor lists.

For every sensor name in an Excel file the script:
1. Creates a global instance DB `{Sensor_Name}_DB` of a configurable source FB.
2. Exports a target LAD FC as SimaticML XML.
3. Injects one new LAD network per sensor (Powerrail → EN of FB call box).
4. Reimports the modified FC, compiles, and saves the project.

---

## Prerequisites

| Requirement | Detail |
|---|---|
| **TIA Portal V19** | Must be installed; project must be open before running the script |
| **Python** | 3.10 or later (64-bit) |
| **pythonnet** | `pip install pythonnet` (≥ 3.0) |
| **openpyxl** | `pip install openpyxl` |
| **Run as Administrator** | Required — TIA Portal Openness refuses non-elevated processes |

---

## Installation

```bash
pip install pythonnet openpyxl
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `TIA_DLL_PATH` | `…\Portal V19\PublicAPI\V19\Siemens.Engineering.dll` | Full path to the Openness API DLL |
| `EXCEL_FILE_PATH` | `sensors.xlsx` (next to `main.py`) | Path to the Excel sensor list |
| `SENSOR_COLUMN_NAME` | `Sensor_Name` | Header of the column containing sensor names |
| `SOURCE_FB_NAME` | `Sensor_FB` | Name of the FB each instance DB instantiates |
| `TARGET_FC_NAME` | `Main_FC` | Name of the LAD FC to inject networks into |
| `BLOCK_GROUP_PATH` | `Sensors` | Block group path relative to root "Program blocks" — use `/` for nesting (e.g. `SubGroup/Sensors`) |
| `EXPORT_DIR` | `exports/` (next to `main.py`) | Temporary directory for the exported FC XML |
| `UID_OFFSET` | `5000` | Starting UID for injected elements — must be above any existing UID in the FC |
| `UID_WINDOW` | `20` | UIDs reserved per injected network |

---

## Excel format

The workbook's **first sheet** must have a header row containing a column named `Sensor_Name` (or whatever `SENSOR_COLUMN_NAME` is set to).  Blank cells in that column are silently skipped.

```
| Sensor_Name  |  ...other columns... |
|--------------|----------------------|
| PressureSensor_01 |              |
| TempSensor_A      |              |
|                   |              |   ← blank row skipped
| FlowSensor_07     |              |
```

---

## Running

1. Open TIA Portal V19 and load your project.
2. **Right-click → Run as Administrator** on your terminal / IDE.
3. Execute:

```bash
python main.py
```

Console output example:

```
============================================================
  TIA Portal V19 Sensor Automation
  Run as Administrator  |  TIA Portal must be open
============================================================

[Step 1] Reading sensor names from Excel
--------------------------------------------------
  Sensors found (3): PressureSensor_01, TempSensor_A, FlowSensor_07

[Step 2] Attached to TIA Portal V19
  [TIA] Found 1 TIA Portal process(es) — attaching to first.
  [TIA] Project : MyPlcProject
  [TIA] PLC software found on device 'PLC_1'.

[Step 3] Creating instance DBs  (source FB: 'Sensor_FB')
    [DB] Created 'PressureSensor_01_DB'.
    [DB] Created 'TempSensor_A_DB'.
    [DB] Created 'FlowSensor_07_DB'.
  → Created: 3   Skipped (already exist): 0

[Step 4] Exporting FC  'Main_FC'
  [FC]  Exported 'Main_FC' → …\exports\Main_FC.xml

[Step 5] Injecting LAD networks into exported FC XML
  → 3 network(s) injected into …\exports\Main_FC.xml

[Step 6] Reimporting modified FC and compiling
  [FC]  Reimported 'Main_FC' from …\exports\Main_FC.xml
  [Compile] Result: Success  (errors=0, warnings=0)

[Step 7] Saving project
  [TIA] Saving project…
  [TIA] Project saved successfully.

============================================================
  Done.  3 sensor(s) processed in 14.3s.
============================================================
```

---

## Project layout

```
tia_sensor_automation/
├── config.py               User settings (paths, names, namespaces)
├── excel_reader.py         Reads sensor names from Excel via openpyxl
├── network_xml_builder.py  Builds and injects SimaticML CompileUnit elements
├── tia_portal.py           TIASession context manager (Openness API wrapper)
├── main.py                 Orchestrates the 4-step workflow
├── sensors.xlsx            Your sensor list (create this — not included)
├── exports/                Temporary FC XML files (auto-created at runtime)
└── README.md               This file
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `No running TIA Portal V19 instance found` | Script not run as Administrator, or portal not open | Right-click terminal → "Run as Administrator"; ensure TIA Portal V19 is open with a project loaded |
| `Could not find a PLC software container` | No PLC device in project, or wrong `device_name` | Add a PLC device in the project or set `device_name=` in `TIASession()` in `main.py` |
| `Column 'Sensor_Name' not found` | Excel header typo or wrong column name | Check the header row of your workbook; update `SENSOR_COLUMN_NAME` in `config.py` |
| `Source FB 'Sensor_FB' not found` | FB does not exist in project | Create the FB in TIA Portal first, or correct `SOURCE_FB_NAME` in `config.py` |
| `Target FC 'Main_FC' not found` | FC does not exist in project | Create the FC in TIA Portal first, or correct `TARGET_FC_NAME` in `config.py` |
| `Block group '…' not found` | Wrong path or group doesn't exist | Verify the block group exists in TIA Portal; update `BLOCK_GROUP_PATH` in `config.py` |
| Compilation errors after import | UID collision or malformed XML | Increase `UID_OFFSET` in `config.py`; inspect the generated XML in `exports/` |
| `ImportError: No module named 'clr'` | pythonnet not installed | `pip install pythonnet` |
| Openness API throws `COMException` | TIA Portal Openness not enabled | Enable "TIA Portal Openness" in TIA Portal → Options → Settings → General |

---

## Technical notes

- **pythonnet** (not COM) is used to call the .NET Openness API directly.
- SimaticML FlgNet namespace: `http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v4`
- Existing instance DBs are detected by name and silently skipped.
- FC export uses `ExportOptions(0)` (no defaults); import uses `ImportOptions.Override`.
- UIDs in injected XML start at `UID_OFFSET` (default 5000) with a `UID_WINDOW` (default 20) wide slot per network.  Collision detection shifts the window upward if needed.
