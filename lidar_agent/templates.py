"""Report layouts, copied from the PGCIL 'Sag and Vegetation Clearance Report' sheets.
Each observation = (Observation Type text, measurement key).  Text is kept exactly as in the
client sheets (typos included) so the output matches your existing reports."""

SUSPENSION = [
    ("Different Phases Clearences", [
        ("Left Conductor  to Middle Conductor ", "phase_LM"),
        ("Right Conductor  to Middle Conductor ", "phase_RM")]),
    ("OPGW to Top \nConductor Clearances", [
        ("OPGW to Right Conductor ", "opgw_R"),
        ("OPGW to Left Conductor", "opgw_L")]),
    ("Conductor to Horizontal Leg \nClearances", [
        ("Left Conductor to Main Leg", "s_L_leg"),
        ("Middle Conductor  to top tower body", "s_M_top"),
        ("Middle Conductor  to Bottom tower body", "s_M_bot"),
        ("Middle Conductor  to left Side tower body", "s_M_left"),
        ("Middle Conductor to Right Side tower body ", "s_M_right"),
        ("Right Conductor  to Main Leg", "s_R_leg")]),
    ("Crossing \nClearances", [
        ("Left  Conductor to Crossing line EW/OPGW", "cross_L"),
        ("Right Conductor to Crossing line EW/OPGW", "cross_R")]),
    ("Fwd Span Ground Clearances", [
        ("Left Conductor Null Point to Ground ", "gnd_L"),
        ("Right Conductor Null Point to Ground ", "gnd_R")]),
    ("Clearance for Structures", [("Clearance for Structures", "structures")]),
]

TENSION = [
    ("Different Phase Clearencs", [
        ("Left Conductor to Middle Conductor ", "phase_LM"),
        ("Right Conductor to Middle Conductor ", "phase_RM")]),
    ("OPGW to Top \nConductor Clearances", [
        ("OPGW to Right Conductor ", "opgw_R"),
        ("OPGW to Left Conductor", "opgw_L")]),
    ("Jumper Drop Clearances", [
        ("Left Cross Arm to Jumper Null Point", "t_L_arm"),
        ("Right Cross Arm to Jumper Null Point", "t_R_arm"),
        ("Middle Upper Cage Arm to Jumper Null Point", "t_M_upper"),
        ("Middle Lower Cage Arm to Jumper Null Point", "t_M_lower")]),
    ("Arcing Horn to Jumper Conductor Clearances", [
        ("Left Lower Arcing Horn to Jumper Condutor", "t_L_horn"),
        ("Middle Lower Arcing Horn to Jumper Condutor", "t_M_horn"),
        ("Right Lower Arcing Horn to Jumper Condutor", "t_R_horn")]),
    ("Jumper to Leg \nClearances", [
        ("Left Jumper to Main Leg", "t_L_leg"),
        ("Middle Jumper to left side tower body", "t_M_left"),
        ("Middle Jumper to right side tower body", "t_M_right"),
        ("Right Jumper to Main Leg", "t_R_leg")]),
    ("Crossing \nClearances", [
        ("Left  Conductor to Crossing line EW/OPGW", "cross_L"),
        ("Right  Conductor to Crossing line EW/OPGW", "cross_R")]),
    ("Crossing \nClearances 2", [
        ("Left  Conductor to Crossing line EW/OPGW", "cross2_L"),
        ("Right  Conductor to Crossing line EW/OPGW", "cross2_R")]),
    ("Fwd Span Ground  Clearances", [
        ("Left Conductor Null Point to Ground ", "gnd_L"),
        ("Right Conductor Null Point to Ground ", "gnd_R")]),
    ("Clearance for Structures", [("Clearance for Structures", "structures")]),
]

OPTIONAL_GROUPS = ("Crossing \nClearances 2",)     # only written when a second crossing was found


def groups(ttype, results):
    """template groups for this report: the second crossing set only appears when there is a second crossing."""
    return [(g, obs) for g, obs in TEMPLATES[ttype]
            if g not in OPTIONAL_GROUPS or any(results.get(k, {}).get("conf") != "na" for _l, k in obs)]


TEMPLATES = {"suspension": SUSPENSION, "tension": TENSION}
TOWER_TYPE_TEXT = {"suspension": "Suspension Tower ", "tension": "Tension Tower "}
