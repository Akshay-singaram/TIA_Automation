"""
Parse an exported GlobalDB SimaticML XML and update <StartValue> elements
inside array-of-struct members.

XML path for each update:
  Section[Name=Static]
    → Member[Name=part1]                 (dot-separated path, e.g. HMI_Params)
      → Member[Name=part2]              (e.g. HMI_Inputs)
        → Member[Name=part3]            (e.g. Statemachine_State  ← the array)
          → Subelement[Path=index]
            → Member[Name=variable_SP]
                → StartValue            set to default_value
            → Member[Name=variable_EN]  (auto-set to true when variable ends in _SP)
                → StartValue            set to true
"""

from xml.dom import minidom


def _child_element(parent, local_name: str, attr: str = None, val: str = None):
    """Return the first direct child element matching local_name and optional attribute."""
    for node in parent.childNodes:
        if node.nodeType != node.ELEMENT_NODE:
            continue
        name = node.localName if node.localName else node.nodeName
        if name == local_name:
            if attr is None or node.getAttribute(attr) == val:
                return node
    return None


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
    e.g. 'HMI_Params.HMI_Inputs.Statemachine_State'
    Returns the final Member node (the array), or None if any part is missing.
    """
    node = static_section
    for part in dot_path.split("."):
        node = _child_element(node, "Member", "Name", part)
        if node is None:
            return None
    return node


def _set_start_value(dom: minidom.Document, member_node, value: str) -> None:
    sv = _child_element(member_node, "StartValue")
    if sv is None:
        sv = dom.createElement("StartValue")
        member_node.appendChild(sv)
    for child in list(sv.childNodes):
        sv.removeChild(child)
    sv.appendChild(dom.createTextNode(value))


def update_db_defaults(xml_path: str, updates: list[dict]) -> int:
    """
    Apply default-value updates to the exported DB XML at xml_path and overwrite it.

    Each entry in updates must have:
      array_name    — dot-separated path to the array Member (e.g. HMI_Params.HMI_Inputs.Statemachine_State)
      array_index   — integer index into the array
      variable_name — struct field name ending in _SP (e.g. HHH_SP)
      default_value — string value for that field's StartValue

    When variable_name ends in _SP, the sibling _EN variable is automatically
    set to true in the same struct instance.

    Returns the number of _SP StartValues successfully updated (each _EN set
    is not counted separately).
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

        array_member = _resolve_dotted_path(static_section, array_path)
        if array_member is None:
            print(f"    [WARN] Path '{array_path}' not found in DB — skipping.")
            continue

        subelement = _child_element(array_member, "Subelement", "Path", array_index)
        if subelement is None:
            subelement = dom.createElement("Subelement")
            subelement.setAttribute("Path", array_index)
            array_member.appendChild(subelement)

        var_member = _child_element(subelement, "Member", "Name", variable_name)
        if var_member is None:
            print(
                f"    [WARN] Variable '{variable_name}' not found at "
                f"'{array_path}[{array_index}]' — skipping."
            )
            continue

        _set_start_value(dom, var_member, default_value)
        print(f"    [DB]  {array_path}[{array_index}].{variable_name} = {default_value}")
        updated += 1

        # Auto-set the corresponding _EN variable to true
        if variable_name.endswith("_SP"):
            en_name = variable_name[:-3] + "_EN"
            en_member = _child_element(subelement, "Member", "Name", en_name)
            if en_member is not None:
                _set_start_value(dom, en_member, "true")
                print(f"    [DB]  {array_path}[{array_index}].{en_name} = true  (auto)")
            else:
                print(f"    [WARN] '{en_name}' not found at index {array_index} — _EN not set.")

    xml_bytes: bytes = dom.toxml(encoding="utf-8")
    with open(xml_path, "wb") as fh:
        fh.write(xml_bytes)

    return updated
