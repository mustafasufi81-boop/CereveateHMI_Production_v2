import urllib.request, json

token = open(r'd:\CereveateHMI_Production\HMI\logs\hmi_app.log.1', 'r', errors='replace').read()
# just hit the API without token to see what we get
try:
    req = urllib.request.Request('http://127.0.0.1:5000/api/alarms/active')
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode())
    alarms = data.get('alarms', [])
    print(f"Total alarms returned by API: {len(alarms)}")
    ay = [a for a in alarms if 'AY1101' in str(a.get('tag_id','')) or 'AY1101' in str(a.get('tag_name',''))]
    print(f"AY1101 in response: {len(ay)}")
    for a in ay:
        print(f"  id={a.get('id')} tag_id={a.get('tag_id')} tag_name={a.get('tag_name')} state={a.get('alarm_state')} sp={a.get('alarm_setpoint')} pv={a.get('alarm_actual_value')}")
    if not ay:
        print("\nFirst 5 alarms in response:")
        for a in alarms[:5]:
            print(f"  tag_id={a.get('tag_id')} state={a.get('alarm_state')}")
except Exception as e:
    print(f"Error: {e}")
