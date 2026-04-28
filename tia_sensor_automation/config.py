import os

# === TIA Portal Openness API ===
TIA_DLL_PATH = (
    r"C:\Program Files\Siemens\Automation\Portal V19"
    r"\PublicAPI\V19\Siemens.Engineering.dll"
)

# === Excel input ===
EXCEL_FILE_PATH = os.path.join(os.path.dirname(__file__), "sensors.xlsx")

# === Excel column headers ===
COL_SENSOR_NAME  = "Sensor_Name"
COL_SOURCE_FB    = "Source_FB"
COL_TARGET_FC    = "Target_FC"
COL_BLOCK_GROUP  = "Block_Group"

# === Runtime export directory ===
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "exports")

# === SimaticML FlgNet namespace (v4 — TIA Portal V14+) ===
FLGNET_NAMESPACE = (
    "http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v4"
)

# === UID allocation for injected networks ===
# Each injected network gets a window of UID_WINDOW consecutive UIDs.
# Base starts at UID_OFFSET so we never collide with hand-authored blocks.
UID_OFFSET = 5000
UID_WINDOW = 20
