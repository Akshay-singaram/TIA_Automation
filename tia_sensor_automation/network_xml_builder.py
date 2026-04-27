"""
Build and inject SimaticML LAD networks into an exported FC XML file.

UID layout per injected network (base = UID_OFFSET + index * UID_WINDOW):
  base + 0  —  Call element
  base + 1  —  Instance element (GlobalVariable)
  base + 2  —  Wire (Powerrail → EN)
  base + 3  —  Comment MultilingualText
  base + 4  —  Comment MultilingualTextItem
  base + 5  —  Title MultilingualText
  base + 6  —  Title MultilingualTextItem
  base + 10 —  CompileUnit element ID itself
"""

import re
from xml.dom import minidom

from config import FLGNET_NAMESPACE, SOURCE_FB_NAME, UID_OFFSET, UID_WINDOW


# ---------------------------------------------------------------------------
# XML template for a single LAD network
# ---------------------------------------------------------------------------

_COMPILE_UNIT_TEMPLATE = """\
<SW.Blocks.CompileUnit ID="{cu_id}" CompositionName="CompileUnits">
  <AttributeList>
    <NetworkSource>
      <FlgNet xmlns="{flgnet_ns}">
        <Parts>
          <Call UId="{call_uid}">
            <CallInfo Name="{fb_name}" BlockType="FB">
              <Instance Scope="GlobalVariable" UId="{inst_uid}">
                <Component Name="{db_name}"/>
              </Instance>
            </CallInfo>
          </Call>
        </Parts>
        <Wires>
          <Wire UId="{wire_uid}">
            <Powerrail/>
            <NameCon UId="{call_uid}" Name="en"/>
          </Wire>
        </Wires>
      </FlgNet>
    </NetworkSource>
    <ProgrammingLanguage>LAD</ProgrammingLanguage>
  </AttributeList>
  <ObjectList>
    <MultilingualText ID="{comment_uid}" CompositionName="Comment">
      <ObjectList>
        <MultilingualTextItem ID="{comment_item_uid}" CompositionName="Items">
          <AttributeList>
            <Culture>en-US</Culture>
            <Text/>
          </AttributeList>
        </MultilingualTextItem>
      </ObjectList>
    </MultilingualText>
    <MultilingualText ID="{title_uid}" CompositionName="Title">
      <ObjectList>
        <MultilingualTextItem ID="{title_item_uid}" CompositionName="Items">
          <AttributeList>
            <Culture>en-US</Culture>
            <Text>{sensor_name}</Text>
          </AttributeList>
        </MultilingualTextItem>
      </ObjectList>
    </MultilingualText>
  </ObjectList>
</SW.Blocks.CompileUnit>"""


def _build_compile_unit_xml(network_index: int, sensor_name: str, fb_name: str) -> str:
    base = UID_OFFSET + network_index * UID_WINDOW
    return _COMPILE_UNIT_TEMPLATE.format(
        cu_id=base + 10,
        call_uid=base,
        inst_uid=base + 1,
        wire_uid=base + 2,
        comment_uid=base + 3,
        comment_item_uid=base + 4,
        title_uid=base + 5,
        title_item_uid=base + 6,
        db_name=f"{sensor_name}_DB",
        sensor_name=sensor_name,
        fb_name=fb_name,
        flgnet_ns=FLGNET_NAMESPACE,
    )


def _collect_existing_ids(dom: minidom.Document) -> set[int]:
    ids: set[int] = set()
    for elem in dom.getElementsByTagName("*"):
        val = elem.getAttribute("ID")
        if val:
            try:
                ids.add(int(val))
            except ValueError:
                pass
    return ids


def _find_fc_object_list(dom: minidom.Document) -> minidom.Element:
    """Return the ObjectList that is a direct child of the SW.Blocks.FC element."""
    fc_nodes = dom.getElementsByTagName("SW.Blocks.FC")
    if not fc_nodes:
        raise ValueError(
            "Could not find <SW.Blocks.FC> in the exported XML.\n"
            "Check that TARGET_FC_NAME points to an existing LAD FC."
        )
    fc_elem = fc_nodes[0]

    for child in fc_elem.childNodes:
        if child.nodeName == "ObjectList":
            return child

    # No ObjectList yet — create one
    obj_list = dom.createElement("ObjectList")
    fc_elem.appendChild(obj_list)
    return obj_list


def inject_networks(xml_path: str, sensor_names: list[str], source_fb_name: str = None) -> int:
    """
    Parse the exported FC XML at *xml_path*, append one new LAD network per
    sensor name, and overwrite the file.  Returns the number of networks added.

    UIDs start at UID_OFFSET and are checked against every existing ID in the
    document; if a collision is detected the window is shifted upward until clear.
    """
    fb_name = source_fb_name or SOURCE_FB_NAME

    dom = minidom.parse(xml_path)
    existing_ids = _collect_existing_ids(dom)
    obj_list = _find_fc_object_list(dom)

    injected = 0
    for idx, sensor_name in enumerate(sensor_names):
        cu_xml = _build_compile_unit_xml(idx, sensor_name, fb_name)

        # Detect and resolve UID collisions (belt-and-suspenders guard)
        base = UID_OFFSET + idx * UID_WINDOW
        shift = 0
        while any((base + shift + offset) in existing_ids for offset in range(UID_WINDOW)):
            shift += UID_WINDOW

        if shift:
            # Re-render with shifted UIDs
            shifted_idx = idx + (shift // UID_WINDOW)
            cu_xml = _build_compile_unit_xml(shifted_idx, sensor_name, fb_name)

        # Register all UIDs from this network so subsequent sensors don't collide
        for offset in range(UID_WINDOW):
            existing_ids.add(base + shift + offset)

        cu_fragment = minidom.parseString(cu_xml).documentElement
        adopted = dom.importNode(cu_fragment, deep=True)
        obj_list.appendChild(adopted)
        injected += 1

    # Write with the same UTF-8 declaration the original had
    xml_bytes: bytes = dom.toxml(encoding="utf-8")
    with open(xml_path, "wb") as fh:
        fh.write(xml_bytes)

    return injected
