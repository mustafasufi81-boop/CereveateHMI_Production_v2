import json, jwt, datetime, urllib.request

cfg = json.load(open('config.json'))
secret = cfg.get('jwt_secret') or cfg.get('security', {}).get('jwt_secret') or 'default_secret'

def make_token(user_id, username, is_admin):
    payload = {
        'user_id': user_id,
        'username': username,
        'is_admin': is_admin,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    return jwt.encode(payload, secret, algorithm='HS256')

def test(label, token, url):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        tags = data.get('tags', [])
        print(f"{label}: HTTP 200 | count={data.get('count')} | tags_is_list={isinstance(tags, list)} | source={data.get('source')}")
        if tags and isinstance(tags, list):
            t = tags[0]
            print(f"  first tag: {t.get('tagId')} = {t.get('value')} [{t.get('quality')}]")
    except urllib.error.HTTPError as e:
        print(f"{label}: HTTP {e.code} - {e.read().decode()[:100]}")
    except Exception as e:
        print(f"{label}: ERROR {e}")

admin_token = make_token(1, 'admin', True)
nonadmin_token = make_token(10, 'Sanjeev Saxena', False)

print("=== /api/opc/values ===")
test("ADMIN    ", admin_token, 'http://localhost:6001/api/opc/values')
test("NON-ADMIN", nonadmin_token, 'http://localhost:6001/api/opc/values')

print("\n=== /api/plc/values ===")
test("ADMIN    ", admin_token, 'http://localhost:6001/api/plc/values')
test("NON-ADMIN", nonadmin_token, 'http://localhost:6001/api/plc/values')
