import urllib.request, json

req = urllib.request.Request('http://localhost:6001/api/auth/login',
    data=json.dumps({'username':'Mustafa','password':'Admin@123'}).encode(),
    headers={'Content-Type':'application/json'})
resp = urllib.request.urlopen(req)
token = json.loads(resp.read())['token']

req2 = urllib.request.Request('http://localhost:6001/api/assets/hierarchy',
    headers={'Authorization': f'Bearer {token}'})
resp2 = urllib.request.urlopen(req2)
data = json.loads(resp2.read())

for plant in data.get('hierarchy', []):
    if plant['name'] == 'FTP-1':
        print('FTP-1 plant:')
        for area in plant.get('children', []):
            name = area['name']
            tc = area['tag_count']
            print(f'  Area: {name} tag_count={tc}')
            for eq in area.get('children', []):
                ename = eq['name']
                etc = eq['tag_count']
                print(f'    Equipment: {ename} tag_count={etc}')
                for sub in eq.get('children', []):
                    print(f'      Sub: {sub["name"]}')
                    for comp in sub.get('children', []):
                        print(f'        Comp: {comp["name"]}')
                        for tag in comp.get('children', []):
                            print(f'          Tag: {tag["id"]} - {tag.get("tag_name")}')
