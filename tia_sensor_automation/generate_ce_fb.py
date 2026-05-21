"""
generate_ce_fb.py — Expand Cause_n_Effect (FB8) from 64 to 200 interlocks.

Interface changes:
  Input:  Cause_1..200, Enable_Cause_1..200, InterlockReset[1..200], InterlockBypass[1..200]
  Output: CSD, InterlockLatchStatus[1..200], InterlockEnableStatus[1..200]

Network (single CompileUnit, 200 iterations):
  For each i = 1..200:
    InterlockReset[i] --| |--> RS[i].R
    Enable_Cause_i    --| |--
    InterlockBypass[i] --|/|--
    InterlockEnableStatus[i] --( )--
    Cause_i           --| |--> RS[i].S1
    RS[i].Q --> CSD --( )--

Run as Administrator with TIA Portal open.
"""

import os
import sys

from config import EXPORT_DIR
from tia_portal import TIASession

COUNT    = 200
FB_NAME  = "Cause_n_Effect"
IFACE_NS = "http://www.siemens.com/automation/Openness/SW/Interface/v5"
FLGNET_NS = "http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v5"


# ---------------------------------------------------------------------------
# Interface XML builder
# ---------------------------------------------------------------------------

def _enable_cause_name(i: int) -> str:
    """Match TIA Portal's existing naming: capital C for index 1, lowercase for 2+."""
    return "Enable_Cause_1" if i == 1 else f"Enable_cause_{i}"


def _build_interface() -> str:
    lines = [f'<Sections xmlns="{IFACE_NS}">', '  <Section Name="Input">']
    for i in range(1, COUNT + 1):
        lines.append(f'    <Member Name="Cause_{i}" Datatype="Bool" />')
    lines.append(f'    <Member Name="InterlockReset" Datatype="Array[1..{COUNT}] of Bool" />')
    lines.append(f'    <Member Name="InterlockBypass" Datatype="Array[1..{COUNT}] of Bool" />')
    for i in range(1, COUNT + 1):
        lines.append(f'    <Member Name="{_enable_cause_name(i)}" Datatype="Bool" />')
    lines += [
        '  </Section>',
        '  <Section Name="Output">',
        '    <Member Name="CSD" Datatype="Bool" />',
        f'    <Member Name="InterlockLatchStatus" Datatype="Array[1..{COUNT}] of Bool" />',
        f'    <Member Name="InterlockEnableStatus" Datatype="Array[1..{COUNT}] of Bool" />',
        '  </Section>',
        '  <Section Name="InOut" />',
        '  <Section Name="Static" />',
        '  <Section Name="Temp" />',
        '  <Section Name="Constant" />',
        '</Sections>',
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# FlgNet XML builder
# ---------------------------------------------------------------------------

def _arr_access(uid: int, name: str, index: int) -> str:
    return (
        f'    <Access Scope="LocalVariable" UId="{uid}">\n'
        f'      <Symbol>\n'
        f'        <Component Name="{name}" AccessModifier="Array">\n'
        f'          <Access Scope="LiteralConstant">\n'
        f'            <Constant>\n'
        f'              <ConstantType>DInt</ConstantType>\n'
        f'              <ConstantValue>{index}</ConstantValue>\n'
        f'            </Constant>\n'
        f'          </Access>\n'
        f'        </Component>\n'
        f'      </Symbol>\n'
        f'    </Access>'
    )


def _var_access(uid: int, name: str) -> str:
    return (
        f'    <Access Scope="LocalVariable" UId="{uid}">\n'
        f'      <Symbol>\n'
        f'        <Component Name="{name}" />\n'
        f'      </Symbol>\n'
        f'    </Access>'
    )


def _build_flgnet() -> str:
    uid = [0]

    def u() -> int:
        uid[0] += 1
        return uid[0]

    parts: list[str] = []
    wires: list[str] = []
    powerrail_targets: list[tuple[int, int]] = []  # (reset_contact_uid, enable_contact_uid)
    rs_uids: list[int] = []                        # RS part UIDs, one per iteration

    for i in range(1, COUNT + 1):
        # --- Accesses ---
        a_reset  = u()
        a_enable = u()
        a_bypass = u()
        a_en_st  = u()
        a_cause  = u()
        a_latch  = u()

        # --- Parts ---
        p_c_reset  = u()
        p_c_enable = u()
        p_c_bypass = u()
        p_coil_en  = u()
        p_c_cause  = u()
        p_rs       = u()

        powerrail_targets.append((p_c_reset, p_c_enable))
        rs_uids.append(p_rs)

        # --- Per-iteration wire UIDs ---
        w_rst_op  = u()
        w_rst_r   = u()
        w_en_op   = u()
        w_en_bp   = u()
        w_bp_op   = u()
        w_bp_coil = u()
        w_enst_op = u()
        w_coil_ca = u()
        w_ca_op   = u()
        w_ca_s1   = u()
        w_latch_op = u()

        parts += [
            _arr_access(a_reset,  "InterlockReset",        i),
            _var_access(a_enable, _enable_cause_name(i)),
            _arr_access(a_bypass, "InterlockBypass",       i),
            _arr_access(a_en_st,  "InterlockEnableStatus", i),
            _var_access(a_cause,  f"Cause_{i}"),
            _arr_access(a_latch,  "InterlockLatchStatus",  i),

            f'    <Part Name="Contact" UId="{p_c_reset}" />',
            f'    <Part Name="Contact" UId="{p_c_enable}" />',
            f'    <Part Name="Contact" UId="{p_c_bypass}">\n'
            f'      <Negated Name="operand" />\n'
            f'    </Part>',
            f'    <Part Name="Coil" UId="{p_coil_en}" />',
            f'    <Part Name="Contact" UId="{p_c_cause}" />',
            f'    <Part Name="Rs" UId="{p_rs}" />',
        ]

        wires += [
            f'    <Wire UId="{w_rst_op}">\n'
            f'      <IdentCon UId="{a_reset}" />\n'
            f'      <NameCon UId="{p_c_reset}" Name="operand" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_rst_r}">\n'
            f'      <NameCon UId="{p_c_reset}" Name="out" />\n'
            f'      <NameCon UId="{p_rs}" Name="r" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_en_op}">\n'
            f'      <IdentCon UId="{a_enable}" />\n'
            f'      <NameCon UId="{p_c_enable}" Name="operand" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_en_bp}">\n'
            f'      <NameCon UId="{p_c_enable}" Name="out" />\n'
            f'      <NameCon UId="{p_c_bypass}" Name="in" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_bp_op}">\n'
            f'      <IdentCon UId="{a_bypass}" />\n'
            f'      <NameCon UId="{p_c_bypass}" Name="operand" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_bp_coil}">\n'
            f'      <NameCon UId="{p_c_bypass}" Name="out" />\n'
            f'      <NameCon UId="{p_coil_en}" Name="in" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_enst_op}">\n'
            f'      <IdentCon UId="{a_en_st}" />\n'
            f'      <NameCon UId="{p_coil_en}" Name="operand" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_coil_ca}">\n'
            f'      <NameCon UId="{p_coil_en}" Name="out" />\n'
            f'      <NameCon UId="{p_c_cause}" Name="in" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_ca_op}">\n'
            f'      <IdentCon UId="{a_cause}" />\n'
            f'      <NameCon UId="{p_c_cause}" Name="operand" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_ca_s1}">\n'
            f'      <NameCon UId="{p_c_cause}" Name="out" />\n'
            f'      <NameCon UId="{p_rs}" Name="s1" />\n'
            f'    </Wire>',

            f'    <Wire UId="{w_latch_op}">\n'
            f'      <IdentCon UId="{a_latch}" />\n'
            f'      <NameCon UId="{p_rs}" Name="operand" />\n'
            f'    </Wire>',
        ]

    # --- OR block, CSD access, CSD coil (shared across all iterations) ---
    a_csd      = u()
    p_or       = u()
    p_coil_csd = u()

    parts += [
        _var_access(a_csd, "CSD"),
        f'    <Part Name="O" UId="{p_or}">\n'
        f'      <TemplateValue Name="Card" Type="Cardinality">{COUNT}</TemplateValue>\n'
        f'    </Part>',
        f'    <Part Name="Coil" UId="{p_coil_csd}" />',
    ]

    # RS[i].q → OR.in{i}
    for i, rs_uid in enumerate(rs_uids, 1):
        w = u()
        wires.append(
            f'    <Wire UId="{w}">\n'
            f'      <NameCon UId="{rs_uid}" Name="q" />\n'
            f'      <NameCon UId="{p_or}" Name="in{i}" />\n'
            f'    </Wire>'
        )

    # OR.out → CSD coil, CSD access → CSD coil operand
    w_or_coil = u()
    w_csd_op  = u()
    wires += [
        f'    <Wire UId="{w_or_coil}">\n'
        f'      <NameCon UId="{p_or}" Name="out" />\n'
        f'      <NameCon UId="{p_coil_csd}" Name="in" />\n'
        f'    </Wire>',

        f'    <Wire UId="{w_csd_op}">\n'
        f'      <IdentCon UId="{a_csd}" />\n'
        f'      <NameCon UId="{p_coil_csd}" Name="operand" />\n'
        f'    </Wire>',
    ]

    # Single powerrail wire fanning out to all reset + enable contacts
    w_pr = u()
    pr_lines = [f'    <Wire UId="{w_pr}">', '      <Powerrail />']
    for p_c_reset, p_c_enable in powerrail_targets:
        pr_lines.append(f'      <NameCon UId="{p_c_reset}" Name="in" />')
        pr_lines.append(f'      <NameCon UId="{p_c_enable}" Name="in" />')
    pr_lines.append('    </Wire>')
    wires.insert(0, '\n'.join(pr_lines))

    return (
        f'<FlgNet xmlns="{FLGNET_NS}">\n'
        '  <Parts>\n' +
        '\n'.join(parts) + '\n'
        '  </Parts>\n'
        '  <Wires>\n' +
        '\n'.join(wires) + '\n'
        '  </Wires>\n'
        '</FlgNet>'
    )


# ---------------------------------------------------------------------------
# XML patching
# ---------------------------------------------------------------------------

def _patch_xml(xml_path: str) -> None:
    with open(xml_path, encoding='utf-8') as f:
        raw = f.read()

    # Replace Interface
    i_start = raw.index('<Interface>')
    i_end   = raw.index('</Interface>') + len('</Interface>')
    raw = raw[:i_start] + '<Interface>' + _build_interface() + '</Interface>' + raw[i_end:]

    # Replace first NetworkSource (the one with actual LAD content)
    ns_start = raw.index('<NetworkSource>')
    ns_end   = raw.index('</NetworkSource>') + len('</NetworkSource>')
    raw = raw[:ns_start] + '<NetworkSource>' + _build_flgnet() + '</NetworkSource>' + raw[ns_end:]

    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(raw)

    print(f"  XML patched: {COUNT} iterations written.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"Expanding '{FB_NAME}' to {COUNT} interlocks...")

    with TIASession() as session:
        print("\n[1] Exporting current FB...")
        xml_path = session.export_fc(FB_NAME)

        print("\n[2] Generating interface and LAD network...")
        _patch_xml(xml_path)

        print("\n[3] Reimporting modified FB...")
        session.import_fc(xml_path, FB_NAME)

        print("\n[4] Compiling...")
        result = session.compile()
        if result.ErrorCount > 0:
            print(f"  WARNING: {result.ErrorCount} compile error(s) — review messages above.")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
