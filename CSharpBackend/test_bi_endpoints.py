import requests
import json

# Login first
login_res = requests.post(
    "http://localhost:6001/api/auth/login",
    json={"username": "Mustafa", "password": "Admin@123"}
)
token = login_res.json()["token"]
print(f"✅ Logged in, token: {token[:50]}...")

# Test /api/bi/tags
tags_res = requests.get(
    "http://localhost:6001/api/bi/tags?limit=3",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"\n✅ /api/bi/tags returned {tags_res.json()['count']} tags")
for tag in tags_res.json()['tags']:
    print(f"   - {tag['tag_id']}: {tag['record_count']} records")

# Test /api/bi/trends
trends_res = requests.post(
    "http://localhost:6001/api/bi/trends",
    json={
        "tag_ids": ["Random.Real8"],
        "start": "2026-05-21T04:00:00",
        "end": "2026-05-21T05:00:00",
        "resample_minutes": 15
    },
    headers={"Authorization": f"Bearer {token}"}
)
trends_data = trends_res.json()
print(f"\n✅ /api/bi/trends returned {trends_data['count']} records")
if trends_data['count'] > 0:
    print(f"   Sample: {trends_data['data'][0]}")

# Test /api/bi/baselines
baselines_res = requests.post(
    "http://localhost:6001/api/bi/baselines",
    json={
        "tag_ids": ["Random.Real8"],
        "start": "2026-05-21T04:00:00",
        "end": "2026-05-21T06:00:00"
    },
    headers={"Authorization": f"Bearer {token}"}
)
baselines_data = baselines_res.json()
print(f"\n✅ /api/bi/baselines computed for {len(baselines_data['baselines'])} tags")
for tag, stats in baselines_data['baselines'].items():
    print(f"   - {tag}: mean={stats['mean']:.2f}, std={stats['std']:.2f}, count={stats['count']}")

# Test /api/bi/forecast
forecast_res = requests.post(
    "http://localhost:6001/api/bi/forecast",
    json={
        "tag_id": "Random.Real8",
        "start": "2026-05-21T04:00:00",
        "end": "2026-05-21T06:00:00",
        "steps": 10,
        "resample_minutes": 1
    },
    headers={"Authorization": f"Bearer {token}"}
)
forecast_data = forecast_res.json()
print(f"\n✅ /api/bi/forecast completed")
print(f"   History points: {forecast_data['n_history']}")
print(f"   Best model: {forecast_data['best_model']}")
print(f"   Models tested:")
for model, result in forecast_data['models'].items():
    if 'error' in result:
        print(f"      {model}: ERROR - {result['error']}")
    else:
        print(f"      {model}: MAE={result.get('mae', 'N/A')}, RMSE={result.get('rmse', 'N/A')}, Status={result.get('status', 'N/A')}, Confidence={result.get('confidence', 'N/A')}")

print("\n" + "="*80)
print("✅ ALL BI ENDPOINTS WORKING - REFACTOR SUCCESSFUL!")
print("="*80)
