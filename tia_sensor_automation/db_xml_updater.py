"""
Parse an exported GlobalDB SimaticML XML and update <StartValue> elements
inside array-of-struct members.

For an array of UDT/struct, TIA Portal encodes both the array index AND the
struct field name in the Subelement Path attribute (dot-separated):

  Section[Name=Static]
    → Member[Name=part1]                      (dot-separated path to array)
      → Member[Name=part2]
        → Member[Name=array_name]             (the array itself)
          → Subelement[Path="index.FieldName"]
              → StartValue                    ← the default value

Example: HMI_Params.HMI_Inputs.StateMachine_State[0].HHH_SP
  Path attribute = "0.HHH_SP"
"""

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
        parent_node.removeChild(child) if False else sv.removeChild(child)
    sv.appendChild(dom.createTextNode(value))


def _get_or_create_subelement(dom: minidom.Document, array_member, path: str):
    """Find or create <Subelement Path="path"> under array_member."""
    sub = _child_element(array_member, "Subelement", "Path", path)
    if sub is None:
        sub = dom.createElement("Subelement")
        sub.setAttribute("Path", path)
        array_member.appendChild(sub)
    return sub


def update_db_defaults(xml_path: str, updates: list[dict]) -> int:
    """
    Apply default-value updates to the exported DB XML at xml_path and overwrite it.

    Each entry in updates must have:
      array_name    — dot-separated path to the array Member
                      (e.g. HMI_Params.HMI_Inputs.StateMachine_State)
      array_index   — integer index into the array
      variable_name — struct field name ending in _SP (e.g. HHH_SP)
      default_value — string value for that field's StartValue

    TIA Portal encodes the field path as "index.FieldName" in the Subelement
    Path attribute — Member elements are not allowed inside Subelement.

    When variable_name ends in _SP, the sibling _EN field is automatically
    set to true in the same Subelement group.

    Returns the number of _SP StartValues successfully updated.
    """
    dom = minidom.parse(xml_path)

    static_section = _find_static_section(dom)
    if static_section is None:
        raise ValueError("Cannot find <Section Name='Static'> in exported DB XML.")

    updated = 0
    for upd in updates:
        array_path    = upd["array_name"]
        array_index   = str(upd["array_index"])
        variable_name = upd["variable_name"]
        default_value = upd["default_value"]

        array_member, failed_part = _resolve_dotted_path(static_section, array_path)
        if array_member is None:
            print(f"    [WARN] Path '{array_path}' not found (failed at '{failed_part}') — skipping.")
            continue

        # Path encodes both index and field: "0.HHH_SP"
        sp_path = f"{array_index}.{variable_name}"
        sp_sub = _get_or_create_subelement(dom, array_member, sp_path)
        _set_start_value(dom, sp_sub, default_value)
        print(f"    [DB]  {array_path}[{array_index}].{variable_name} = {default_value}")
        updated += 1

        # Auto-set the corresponding _EN field to true
        if variable_name.endswith("_SP"):
            en_name = variable_name[:-3] + "_EN"
            en_path = f"{array_index}.{en_name}"
            en_sub = _get_or_create_subelement(dom, array_member, en_path)
            _set_start_value(dom, en_sub, "true")
            print(f"    [DB]  {array_path}[{array_index}].{en_name} = true  (auto)")

    xml_bytes: bytes = dom.toxml(encoding="utf-8")
    with open(xml_path, "wb") as fh:
        fh.write(xml_bytes)

    return updated
