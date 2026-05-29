from app import app
import sys

print('✓ App imported')
print(f'✓ Routes containing "simple": {[r.rule for r in app.url_map.iter_rules() if "simple" in r.rule.lower()]}')

# Test request
with app.test_client() as client:
    print('\n[Testing /api/bi/simple_daily_metrics...]')
    resp = client.get('/api/bi/simple_daily_metrics?start_date=2024-07-21&end_date=2024-07-21&production_tag=TURBINE_LOADMW&coal_tag=TOTAL_COAL_FLOW&steam_tag=MAIN_STEAM_FLOWTPH&rated_capacity=270')
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.get_json()}')
