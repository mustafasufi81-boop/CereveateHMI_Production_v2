import json

with open('tags_to_insert.json') as f:
    tags = json.load(f)

SKIP = set()  # Include ALL tags — full replacement program

# Manually add the 5 existing tags with their known ranges
EXISTING_5 = [
    {'tag_id': 'PY1101A', 'description': 'CHUTE SILO FAN OUTLET PRESSURE #1', 'eng_unit': 'KPA', 'alarm_ll_limit': 0.6, 'alarm_l_limit': 0.8, 'alarm_h_limit': 1.4, 'alarm_hh_limit': 1.6},
    {'tag_id': 'PY1101B', 'description': 'CHUTE SILO FAN OUTLET PRESSURE #2', 'eng_unit': 'KPA', 'alarm_ll_limit': 0.8, 'alarm_l_limit': 0.9, 'alarm_h_limit': 1.3, 'alarm_hh_limit': 1.4},
    {'tag_id': 'PY1103A', 'description': 'ID FAN OUTLET PRESSURE #1',         'eng_unit': 'KPA', 'alarm_ll_limit': 12.0,'alarm_l_limit': 14.0,'alarm_h_limit': 20.0,'alarm_hh_limit': 22.0},
    {'tag_id': 'PY1103B', 'description': 'ID FAN OUTLET PRESSURE #2',         'eng_unit': 'KPA', 'alarm_ll_limit': 14.0,'alarm_l_limit': 15.0,'alarm_h_limit': 18.0,'alarm_hh_limit': 19.0},
    {'tag_id': 'TY1101A', 'description': '1# ID FAN FRONT BEARING TEMPERATURE','eng_unit': '°C',  'alarm_ll_limit': 45.0,'alarm_l_limit': 50.0,'alarm_h_limit': 68.0,'alarm_hh_limit': 72.0},
]

# Default ranges for tags with NULL alarm limits (by unit)
UNIT_DEFAULTS = {
    'Hz':    (0.0,  60.0,  50.0,  55.0),   # LL, HH, lo_sim, hi_sim
    '%':     (0.0, 100.0,  20.0,  80.0),
    'Amp':   (0.0, 100.0,  10.0,  80.0),
    'mm/s':  (0.0,  10.0,   0.5,   7.0),
    'm3/h':  (0.0, 500.0,  50.0, 400.0),
    'Nm3/Hr':(0.0,5000.0, 500.0,4000.0),
    'Ton/h': (0.0, 200.0,  20.0, 160.0),
    'MT':    (0.0,1000.0, 100.0, 800.0),
    'mg/m3': (0.0, 100.0,   5.0,  80.0),
    'M':     (0.0,  10.0,   1.0,   8.0),
    'KPA':   (0.0,  50.0,   5.0,  40.0),
    '°C':    (0.0, 150.0,  30.0, 120.0),
}

lines_var = []
lines_body = []

all_tags = EXISTING_5 + tags

for t in all_tags:
    tid = t['tag_id']
    if tid in SKIP:
        continue

    unit = t['eng_unit']
    hh = t['alarm_hh_limit']
    ll = t['alarm_ll_limit']
    h  = t['alarm_h_limit']
    l  = t['alarm_l_limit']

    if hh is None or ll is None:
        # Use unit defaults, simulate within normal range (no alarm)
        ud = UNIT_DEFAULTS.get(unit, (0.0, 100.0, 10.0, 80.0))
        sim_lo = ud[2]
        sim_hi = ud[3]
    else:
        # Simulate ACROSS alarm limits: go from LL*0.8 to HH*1.15
        # This will trigger L, LL, H, HH alarms during oscillation
        sim_lo = round(ll * 0.80, 4)
        sim_hi = round(hh * 1.15, 4)
        if sim_lo < 0:
            sim_lo = 0.0

    step = round((sim_hi - sim_lo) / 150.0, 6)
    if step == 0:
        step = 0.01
    init = round((sim_lo + sim_hi) / 2.0, 4)

    lines_var.append(f"    {tid}       : REAL := {init};")
    lines_var.append(f"    Dir_{tid}   : BOOL := 1;")

    lines_body.append(f"    (* {tid} - {t['description']} [{unit}] sim {sim_lo}..{sim_hi} *)")
    lines_body.append(f"    IF Dir_{tid} THEN")
    lines_body.append(f"        {tid} := {tid} + {step};")
    lines_body.append(f"    ELSE")
    lines_body.append(f"        {tid} := {tid} - {step};")
    lines_body.append(f"    END_IF;")
    lines_body.append(f"    IF {tid} >= {sim_hi} THEN Dir_{tid} := 0; END_IF;")
    lines_body.append(f"    IF {tid} <= {sim_lo} THEN Dir_{tid} := 1; END_IF;")
    lines_body.append(f"")

var_block = "\n".join(lines_var)
body_block = "\n".join(lines_body)

out = f"""(* ============================================================
   FTP-1 POTLINE Simulation Program — FULL REPLACEMENT
   Auto-generated from Tag_master_Details_System_Upload.xlsx
   TOTAL TAGS: {len(all_tags)} (includes all 5 existing + 123 new)
   Set Sim_Enable := 1 to start, 0 to stop.
   Tags with NULL limits simulate within normal range only.
   All other tags oscillate across LL/HH -> triggers alarms.
   ============================================================ *)

VAR
    Sim_Enable  : BOOL := 0;

    (* --- Simulated tag variables --- *)
{var_block}
END_VAR

(* ============================================================
   SIMULATION BODY
   ============================================================ *)
IF Sim_Enable THEN

{body_block}
END_IF;
"""

with open('FTP1_Simulation.st', 'w') as f:
    f.write(out)

# Count stats
null_count = sum(1 for t in all_tags if t['alarm_hh_limit'] is None)
alarm_count = sum(1 for t in all_tags if t['alarm_hh_limit'] is not None)
print(f"Generated FTP1_Simulation.st  (FULL REPLACEMENT)")
print(f"  Total tags : {len(all_tags)}")
print(f"    -> With alarm range (cross LL/HH) : {alarm_count}")
print(f"    -> With NULL limits (normal range) : {null_count}")
