"""
Parse an exported GlobalDB/InstanceDB SimaticML XML and update <StartValue>
elements inside array-of-struct members.

TIA Portal's IndexPath_TP only allows numeric indices in the Subelement Path,
and Subelement may only contain StartValue (not Member children). For an
Array of UDT/Struct, individual field defaults are expressed as an IEC 61131-3
struct literal in the single StartValue of the numeric-indexed Subelement:

  Section[Name=Static]
    → Member[Name=part1]                   (dot-separated path to array)
      → Member[Name=part2]
        → Member[Name=array_name]          (the array itself)
          → Subelement[Path="0"]           (numeric index only)
              → StartValue                 "(HHH_SP:=588, HHH_EN:=TRUE)"

Multiple Excel rows targeting the same (array, index) are merged into one
struct literal before writing.
"""

from collections import defaultdict
from xml.dom import minidom


def _child_element(parent, local_name: str, attr: str = None, val: str = None):
    """Return the first direct child element matching local_name.
    Attribute value comparison is case-insensitive."""
    for node in parent.childNodes:
        if node.nodeType != node.ELEMENT_NODE:
            continue
        name = node.localName if node.localName else node.nodeName
        if name == local_name:
            if attr is None or node.getAttribute(attr).lower() == val.lower():
                return node
    return None


def _child_member_names(parent) -> list[str]:
    """Return all direct child Member names — used in warnings."""
    return [
        node.getAttribute("Name")
        for node in parent.childNodes
        if node.nodeType == node.ELEMENT_NODE
        and (node.localName or node.nodeName) == "Member"
    ]


def _find_static_section(dom: minidom.Document):
    """Return <Section Name="Static"> from the DB's Interface."""
    for sections_node in dom.getElementsByTagName("Sections"):
        static = _child_element(sections_node, "Section", "Name", "Static")
        if static is not None:
            return static
    return None


def _resolve_dotted_path(static_section, dot_path: str):
    """
    Navigate a dot-separated Member path from the Static section.
    e.g. 'HMI_Params.HMI_Inputs.StateMachine_State'
    Name matching is case-insensitive.
    Returns (final_node, None) on success, or (None, failed_part) on failure.
    """
    node = static_section
    for part in dot_path.split("."):
        child = _child_element(node, "Member", "Name", part)
        if child is None:
            available = _child_member_names(node)
            print(f"    [WARN] '{part}' not found. Available: {available}")
            return None, part
        node = child
    return node, None


def _set_start_value(dom: minidom.Document, parent_node, value: str) -> None:
    """Set or create <StartValue> text inside parent_node."""
    sv = _child_element(parent_node, "StartValue")
    if sv is None:
        sv = dom.createElement("StartValue")
        parent_node.appendChild(sv)
    for child in list(sv.childNodes):
        sv.removeChild(child)
    sv.appendChild(dom.createTextNode(value))


def _get_or_create_subelement(dom: minidom.Document, array_member, path: str):
    """Find or create <Subelement Path="path"> under array_member."""
    sub = _child_element(array_member, "Subelement", "Path", path)
    if sub is None:
        sub = dom.createElement("Subelement")
        sub.setAttribute("Path", path)
        array_member.appendChild(sub)
    return sub


def _build_struct_literal(fields: dict[str, str]) -> str:
    """
    Build an IEC 61131-3 struct literal from a field→value dict.
    e.g. {'HHH_SP': '588', 'HHH_EN': 'TRUE'} → '(HHH_SP:=588, HHH_EN:=TRUE)'
    """
    parts = ", ".join(f"{k}:={v}" for k, v in fields.items())
    return f"({parts})"


def update_db_defaults(xml_path: str, updates: list[dict]) -> int:
    """
    Apply default-value updates to the exported DB XML at xml_path and overwrite it.

    Each entry in updates must have:
      array_name    — dot-separated path to the array Member
                      (e.g. HMI_Params.HMI_Inputs.StateMachine_State)
      array_index   — integer index into the array
      variable_name — struct field name (e.g. HHH_SP)
      default_value — value string for that field

    When variable_name ends in _SP, the sibling _EN field is automatically
    included in the struct literal with value TRUE.

    Multiple rows targeting the same (array_path, array_index) are merged
    into a single struct literal: (HHH_SP:=588, HHH_EN:=TRUE, HH_SP:=150, ...).

    Returns the number of Subelements (array indices) written.
    """
    dom = minidom.parse(xml_path)

    static_section = _find_static_section(dom)
    if static_section is None:
        raise ValueError("Cannot find <Section Name='Static'> in exported DB XML.")

    # Group: array_path → index → {field: value}
    # Preserve insertion order so struct literal matches Excel row order
    grouped: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))

    for upd in updates:
        array_path    = upd["array_name"]
        array_index   = str(upd["array_index"])
        variable_name = upd["variable_name"]
        default_value = upd["default_value"]

        grouped[array_path][array_index][variable_name] = default_value

        if variable_name.endswith("_SP"):
            en_name = variable_name[:-3] + "_EN"
            grouped[array_path][array_index][en_name] = "TRUE"

    subelements_written = 0

    for array_path, index_map in grouped.items():
        array_member, failed_part = _resolve_dotted_path(static_section, array_path)
        if array_member is None:
            print(f"    [WARN] Path '{array_path}' not found (failed at '{failed_part}') — skipping.")
            continue

        for array_index, fields in index_map.items():
            struct_literal = _build_struct_literal(fields)
            sub = _get_or_create_subelement(dom, array_member, array_index)
            _set_start_value(dom, sub, struct_literal)

            for field, value in fields.items():
                label = "auto" if field.endswith("_EN") else ""
                suffix = f"  ({label})" if label else ""
                print(f"    [DB]  {array_path}[{array_index}].{field} = {value}{suffix}")
            subelements_written += 1

    xml_bytes: bytes = dom.toxml(encoding="utf-8")
    with open(xml_path, "wb") as fh:
        fh.write(xml_bytes)

    return subelements_written
