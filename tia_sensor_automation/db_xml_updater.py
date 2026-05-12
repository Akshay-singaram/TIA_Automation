"""
Parse an exported GlobalDB SimaticML XML and update <StartValue> elements
inside array-of-struct members.

XML path for each update:
  Section[Name=Static]
    → Member[Name=array_name]          (the array)
      → Subelement[Path=array_index]   (the struct instance at that index)
        → Member[Name=variable_name]   (the struct field)
          → StartValue                 (the default value text)
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
      array_name    — name of the array Member in the Static section
      array_index   — integer index into the array
      variable_name — name of the struct field within that element
      default_value — string representation of the new StartValue

    Returns the number of StartValues successfully updated.
    """
    dom = minidom.parse(xml_path)

    static_section = _find_static_section(dom)
    if static_section is None:
        raise ValueError("Cannot find <Section Name='Static'> in exported DB XML.")

    updated = 0
    for upd in updates:
        array_name    = upd["array_name"]
        array_index   = str(upd["array_index"])
        variable_name = upd["variable_name"]
        default_value = upd["default_value"]

        array_member = _child_element(static_section, "Member", "Name", array_name)
        if array_member is None:
            print(f"    [WARN] Array '{array_name}' not found in DB — skipping.")
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
                f"'{array_name}[{array_index}]' — skipping."
            )
            continue

        _set_start_value(dom, var_member, default_value)
        print(f"    [DB]  {array_name}[{array_index}].{variable_name} = {default_value}")
        updated += 1

    xml_bytes: bytes = dom.toxml(encoding="utf-8")
    with open(xml_path, "wb") as fh:
        fh.write(xml_bytes)

    return updated
