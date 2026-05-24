import subprocess, time, urllib.request
cwd = r"D:\Development\MQTT_Implemented_OPC\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206\DB_Query"
proc = subprocess.Popen(['python', 'historian_query_tool.py'], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
try:
    time.sleep(4)
    try:
        with urllib.request.urlopen('http://127.0.0.1:7005/api/stats/total', timeout=20) as r:
            data = r.read().decode('utf-8')
        print('API response:', data)
    except Exception as e:
        print('API call failed:', repr(e))
    out, err = proc.communicate(timeout=10)
    print('stdout:', out)
    print('stderr:', err)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
