from openpyxl import load_workbook

from config import (
    COL_BLOCK_GROUP,
    COL_SENSOR_NAME,
    COL_SOURCE_FB,
    COL_TARGET_FC,
    EXCEL_FILE_PATH,
)

REQUIRED_COLUMNS = [COL_SENSOR_NAME, COL_SOURCE_FB, COL_TARGET_FC, COL_BLOCK_GROUP]


def read_sensor_rows(file_path: str | None = None) -> list[dict]:
    """
    Read sensor/actuator rows from the first sheet of an Excel workbook.

    Required columns (set in config.py):
      COL_SENSOR_NAME  — name of the sensor or actuator
      COL_SOURCE_FB    — FB to instantiate for this row
      COL_TARGET_FC    — LAD FC to inject the network into
      COL_BLOCK_GROUP  — block group path for the instance DB

    Rows where Sensor_Name is blank are silently skipped.
    Returns a list of dicts with keys: sensor_name, source_fb, target_fc, block_group.
    """
    path = file_path or EXCEL_FILE_PATH

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise ValueError(f"Workbook '{path}' has no active sheet.")

    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if header_row is None:
        raise ValueError(f"Workbook '{path}' appears to be empty.")

    headers = [str(h).strip() if h is not None else "" for h in header_row]

    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise ValueError(
            f"Missing column(s) in '{path}': {missing}\n"
            f"  Headers found: {headers}"
        )

    idx = {col: headers.index(col) for col in REQUIRED_COLUMNS}

    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        sensor = row[idx[COL_SENSOR_NAME]] if idx[COL_SENSOR_NAME] < len(row) else None
        if sensor is None or not str(sensor).strip():
            continue
        rows.append({
            "sensor_name": str(sensor).strip(),
            "source_fb":   str(row[idx[COL_SOURCE_FB]]).strip(),
            "target_fc":   str(row[idx[COL_TARGET_FC]]).strip(),
            "block_group": str(row[idx[COL_BLOCK_GROUP]]).strip(),
        })

    wb.close()
    return rows
