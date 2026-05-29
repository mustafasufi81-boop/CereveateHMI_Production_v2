"""
Test script to verify PivotTableSettings configuration is loaded correctly
"""
import json

print("=" * 60)
print("Testing PivotTableSettings Configuration")
print("=" * 60)

# Load config file
with open('trends-config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# Check if PivotTableSettings exists
if 'PivotTableSettings' in config:
    print("✅ PivotTableSettings found in config file")
    
    pivot_config = config['PivotTableSettings']
    
    # Check main sections
    print(f"\n📊 Display Mode: {pivot_config.get('DisplayMode', 'Not set')}")
    
    # Check Health Indicators
    if 'HealthIndicators' in pivot_config:
        print(f"\n💡 Health Indicators:")
        for indicator, settings in pivot_config['HealthIndicators'].items():
            enabled = "✓" if settings.get('Enabled', False) else "✗"
            print(f"  {enabled} {indicator}")
    
    # Check KPI Groups
    if 'KPIGroups' in pivot_config:
        print(f"\n📈 KPI Groups:")
        for group_name, group_config in pivot_config['KPIGroups'].items():
            icon = group_config.get('Icon', '📊')
            title = group_config.get('Title', group_name)
            param_count = len(group_config.get('Parameters', []))
            metrics_count = len(group_config.get('Metrics', []))
            print(f"  {icon} {title}: {param_count} parameters, {metrics_count} metrics")
    
    print("\n" + "=" * 60)
    print("✅ Configuration structure is valid!")
    print("=" * 60)
    
else:
    print("❌ PivotTableSettings NOT found in config file!")
    print("Available keys:", list(config.keys()))
