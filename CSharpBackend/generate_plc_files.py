import json

with open('tags_to_insert.json') as f:
    tags = json.load(f)

EXISTING_5 = [
    {'tag_id': 'PY1101A', 'description': 'CHUTE SILO FAN OUTLET PRESSURE #1',  'eng_unit': 'KPA', 'alarm_ll_limit': 0.6,  'alarm_h_limit': 1.4,  'alarm_hh_limit': 1.6},
    {'tag_id': 'PY1101B', 'description': 'CHUTE SILO FAN OUTLET PRESSURE #2',  'eng_unit': 'KPA', 'alarm_ll_limit': 0.8,  'alarm_h_limit': 1.3,  'alarm_hh_limit': 1.4},
    {'tag_id': 'PY1103A', 'description': 'ID FAN OUTLET PRESSURE #1',          'eng_unit': 'KPA', 'alarm_ll_limit': 12.0, 'alarm_h_limit': 20.0, 'alarm_hh_limit': 22.0},
    {'tag_id': 'PY1103B', 'description': 'ID FAN OUTLET PRESSURE #2',          'eng_unit': 'KPA', 'alarm_ll_limit': 14.0, 'alarm_h_limit': 18.0, 'alarm_hh_limit': 19.0},
    {'tag_id': 'TY1101A', 'description': '1# ID FAN FRONT BEARING TEMPERATURE','eng_unit': '°C',  'alarm_ll_limit': 45.0, 'alarm_h_limit': 68.0, 'alarm_hh_limit': 72.0},
]

UNIT_DEFAULTS = {
    'Hz':    (50.0,  55.0),  '%':     (20.0,  80.0),  'Amp':   (10.0,  80.0),
    'mm/s':  (0.5,   7.0),   'm3/h':  (50.0,  400.0), 'Nm3/Hr':(500.0, 4000.0),
    'Ton/h': (20.0,  160.0), 'MT':    (100.0, 800.0),  'mg/m3': (5.0,   80.0),
    'M':     (1.0,   8.0),   'KPA':   (5.0,   40.0),   '°C':    (30.0,  120.0),
}

all_tags = EXISTING_5 + tags

# ── 1. Studio 5000 Tag Import CSV ─────────────────────────────────────────────
# Only REAL tags for values + ONE shared sim_step + ONE BOOL Sim_Enable
csv_lines = ['Name,Data Type,Description,External Access,Style']
csv_lines.append('sim_step,REAL,Simulation angle step 0..6.28,Read/Write,Float')
csv_lines.append('Sim_Enable,BOOL,Set 1 to enable simulation,Read/Write,Decimal')
for t in all_tags:
    tid  = t['tag_id']
    desc = t.get('description','').replace(',', ' ')
    csv_lines.append(f'{tid},REAL,{desc},Read/Write,Float')

with open('FTP1_Tags_Import.csv', 'w') as f:
    f.write('\n'.join(csv_lines))
print(f"FTP1_Tags_Import.csv  → {len(all_tags) + 2} entries ({len(all_tags)} REAL + sim_step + Sim_Enable)")

# ── 2. ST Body — SIN-based, same pattern as welding simulation ────────────────
body_lines = []
body_lines.append('(* ----------------------------------------------------')
body_lines.append(' * FTP-1 POTLINE Simulation')
body_lines.append(' * Same pattern as welding sim: one sim_step, SIN-based')
body_lines.append(' * Runs in main task. Set Sim_Enable := 1 to activate.')
body_lines.append(' * ----------------------------------------------------*)')
body_lines.append('')
body_lines.append('IF Sim_Enable THEN')
body_lines.append('')
body_lines.append('    (* Advance shared angle — same as welding sim_step *)')
body_lines.append('    sim_step := sim_step + 0.07;')
body_lines.append('    IF sim_step > 6.28 THEN sim_step := 0.0; END_IF;')
body_lines.append('')

for i, t in enumerate(all_tags):
    tid  = t['tag_id']
    unit = t.get('eng_unit', 'KPA')
    hh   = t.get('alarm_hh_limit')
    ll   = t.get('alarm_ll_limit')
    h    = t.get('alarm_h_limit')

    if hh is None or ll is None:
        ud   = UNIT_DEFAULTS.get(unit, (5.0, 80.0))
        lo, hi = ud
    else:
        lo = round(ll * 0.85, 4)
        hi = round(hh * 1.10, 4)
        if lo < 0: lo = 0.0

    base = round((lo + hi) / 2.0, 4)
    amp  = round((hi - base) * 0.95, 4)  # reaches into alarm zone
    # phase offset per tag so they don't all peak together
    phase = round((i % 16) * 0.39, 2)   # 0.39 ≈ 6.28/16

    body_lines.append(f'    (* {tid} [{unit}] base={base} ±{amp} range {lo}..{hi} *)')
    body_lines.append(f'    {tid} := {base} + (SIN(sim_step + {phase}) * {amp});')
    body_lines.append('')

body_lines.append('ELSE')
body_lines.append('')
body_lines.append('    (* Sim OFF — reset step only, keep last values *)')
body_lines.append('    sim_step := 0.0;')
body_lines.append('')
body_lines.append('END_IF;')

with open('FTP1_ST_Body.st', 'w') as f:
    f.write('\n'.join(body_lines))

print(f"FTP1_ST_Body.st       → {len(body_lines)} lines")
print(f"\nInstructions:")
print(f"  Step 1: Import FTP1_Tags_Import.csv  → adds {len(all_tags)} REAL tags + sim_step + Sim_Enable")
print(f"  Step 2: Paste FTP1_ST_Body.st into ST routine (no VAR block, no Dir_ bools)")
print(f"  Step 3: Set Sim_Enable := 1 online to start")
