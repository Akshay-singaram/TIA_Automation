import os

# === TIA Portal Openness API ===
TIA_DLL_PATH = (
    r"C:\Program Files\Siemens\Automation\Portal V19"
    r"\PublicAPI\V19\Siemens.Engineering.dll"
)

# === Excel input ===
EXCEL_FILE_PATH = os.path.join(os.path.dirname(__file__), "sensors.xlsx")
SENSOR_COLUMN_NAME = "Sensor_Name"

# === Source FB that each sensor DB will instantiate ===
SOURCE_FB_NAME = "Sensor_FB"

# === Target LAD FC to inject networks into ===
TARGET_FC_NAME = "Main_FC"

# === Block group path (relative to root "Program blocks") ===
# Use "/" for nesting, e.g. "Sensors" or "SubGroup/Sensors"
BLOCK_GROUP_PATH = "Sensors"

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
