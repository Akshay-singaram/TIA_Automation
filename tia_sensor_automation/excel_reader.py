from openpyxl import load_workbook

from config import EXCEL_FILE_PATH, SENSOR_COLUMN_NAME


def read_sensor_names(file_path: str = None, column_name: str = None) -> list[str]:
    """
    Read non-blank sensor names from the first sheet of an Excel workbook.

    Expects a header row whose first matching cell equals *column_name*.
    Returns a list of stripped strings in sheet order.
    """
    path = file_path or EXCEL_FILE_PATH
    col = column_name or SENSOR_COLUMN_NAME

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if header_row is None:
        raise ValueError(f"Workbook '{path}' appears to be empty.")

    header_list = [str(h).strip() if h is not None else "" for h in header_row]
    if col not in header_list:
        raise ValueError(
            f"Column '{col}' not found in '{path}'.\n"
            f"  Headers detected: {header_list}"
        )
    col_idx = header_list.index(col)

    sensors: list[str] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if col_idx >= len(row):
            continue
        value = row[col_idx]
        if value is not None and str(value).strip():
            sensors.append(str(value).strip())

    wb.close()
    return sensors
