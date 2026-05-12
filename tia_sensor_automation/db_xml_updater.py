"""
Parse an exported GlobalDB/InstanceDB SimaticML XML and update SetPoint
default values inside array-of-struct members.

TIA Portal's correct XML structure for array-of-UDT SetPoint start values
groups by FIELD first, then by array index (not the other way around):

  Member[Name=array]              (the array itself, e.g. StateMachine_State)
    Sections
      Section[Name="None"]
        Member[Name=field]        (struct field, e.g. HHH_SP)
          Subelement[Path="0"]   (array index — numeric only)
            StartValue            the default value
          Subelement[Path="1"]
            StartValue
        Member[Name=field2]
          Subelement[Path="0"]
            StartValue
"""

from collections import defaultdict
from xml.dom import minidom

INTERFACE_NS = "http://www.siemens.com/automation/Openness/SW/Interface/v5"


# ---------------------------------------------------------------------------
# DOM helpers
# ---------------------------------------------------------------------------

def _child_element(parent, local_name: str, attr: str = None, val: str = None):
    """Return first direct child element matching local_name (case-insensitive attr match)."""
    for node in parent.childNodes:
        if node.nodeType != node.ELEMENT_NODE:
            continue
        name = node.localName if node.localName else node.nodeName
        if name == local_name:
            if attr is None or node.getAttribute(attr).lower() == val.lower():
                return node
    return None


def _child_member_names(parent) -> list[str]:
    return [
        node.getAttribute("Name")
        for node in parent.childNodes
        if node.nodeType == node.ELEMENT_NODE
        and (node.localName or node.nodeName) == "Member"
    ]


def _get_or_create(dom: minidom.Document, parent, tag: str, attr: str = None, val: str = None):
    """Find or create a direct child element, using the interface namespace."""
    existing = _child_element(parent, tag, attr, val)
    if existing is not None:
        return existing
    elem = dom.createElementNS(INTERFACE_NS, tag)
    if attr:
        elem.setAttribute(attr, val)
    parent.appendChild(elem)
    return elem


def _infer_datatype(field_name: str, sample_value: str) -> str:
    """Infer Datatype for a new field Member based on name and value."""
    if field_name.endswith("_EN"):
        return "Bool"
    if sample_value.strip().upper() in ("TRUE", "FALSE"):
        return "Bool"
    return "Real"


def _set_start_value(dom: minidom.Document, subelement, value: str) -> None:
    sv = _child_element(subelement, "StartValue")
    if sv is None:
        sv = dom.createElementNS(INTERFACE_NS, "StartValue")
        subelement.appendChild(sv)
    for child in list(sv.childNodes):
        sv.removeChild(child)
    sv.appendChild(dom.createTextNode(value))


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def _find_static_section(dom: minidom.Document):
    for sections_node in dom.getElementsByTagName("Sections"):
        static = _child_element(sections_node, "Section", "Name", "Static")
        if static is not None:
            return static
    return None


def _resolve_dotted_path(static_section, dot_path: str):
    """
    Navigate a dot-separated Member path from the Static section (case-insensitive).
    Returns (final_node, None) on success or (None, failed_part) on failure.
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


# ---------------------------------------------------------------------------
# Main update function
# ---------------------------------------------------------------------------

def update_db_defaults(xml_path: str, updates: list[dict]) -> int:
    """
    Apply default-value updates to the exported DB XML at xml_path and overwrite it.

    Each entry in updates must have:
      array_name    — dot-separated path to the array Member
                      (e.g. HMI_Params.HMI_Inputs.StateMachine_State)
      array_index   — integer index into the array
      variable_name — struct field name (e.g. HHH_SP)
      default_value — value string

    When variable_name ends in _SP, the sibling _EN field is automatically
    set to TRUE at the same index.

    The generated XML structure matches TIA Portal's native export format:
      array Member → Sections → Section[None] → Member[field] → Subelement[index] → StartValue

    Returns the number of StartValues written.
    """
    dom = minidom.parse(xml_path)

    static_section = _find_static_section(dom)
    if static_section is None:
        raise ValueError("Cannot find <Section Name='Static'> in exported DB XML.")

    # Group: array_path → field_name → {index_str: value}
    # Insertion order preserved so fields appear in Excel order
    field_groups: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))

    for upd in updates:
        array_path = upd["array_name"]
        idx        = str(upd["array_index"])
        field      = upd["variable_name"]
        value      = upd["default_value"]

        if field.endswith("_SP"):
            try:
                value = f"{float(value):.1f}" if "." not in str(value) else str(value)
            except (ValueError, TypeError):
                pass
            en_field = field[:-3] + "_EN"
            field_groups[array_path][en_field][idx] = "TRUE"

        field_groups[array_path][field][idx] = value

    written = 0

    for array_path, field_map in field_groups.items():
        array_member, failed_part = _resolve_dotted_path(static_section, array_path)
        if array_member is None:
            print(f"    [WARN] Path '{array_path}' not found (failed at '{failed_part}') — skipping.")
            continue

        # Build: array_member → Sections → Section[None]
        sections    = _get_or_create(dom, array_member, "Sections")
        section_none = _get_or_create(dom, sections, "Section", "Name", "None")

        for field_name, index_map in field_map.items():
            field_member = _get_or_create(dom, section_none, "Member", "Name", field_name)
            if not field_member.getAttribute("Datatype"):
                field_member.setAttribute("Datatype", _infer_datatype(field_name, next(iter(index_map.values()))))

            for idx, value in index_map.items():
                subelement = _get_or_create(dom, field_member, "Subelement", "Path", idx)
                _set_start_value(dom, subelement, value)

                label = "  (auto)" if field_name.endswith("_EN") else ""
                print(f"    [DB]  {array_path}[{idx}].{field_name} = {value}{label}")
                written += 1

    xml_bytes: bytes = dom.toxml(encoding="utf-8")
    with open(xml_path, "wb") as fh:
        fh.write(xml_bytes)

    return written
