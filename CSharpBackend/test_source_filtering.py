"""
Test source filtering logic - verify cascade behavior
"""

# Simulated data from API (like areasQuery.data)
areasData = [
    {"plant": "Plant1", "area": "Area1", "server_progid": "Matrikon.OPC.Simulation.1"},
    {"plant": "Plant1", "area": "Area2", "server_progid": "Matrikon.OPC.Simulation.1"},
    {"plant": "Plant2", "area": "Area3", "server_progid": "PLC_GATEWAY_01"},
    {"plant": "Plant2", "area": "Area4", "server_progid": "PLC_GATEWAY_01"},
    {"plant": "Plant3", "area": "Area5", "server_progid": "PLC_SENSORS_01"},
]

def get_unique_sources(data):
    """All unique sources (no filter)"""
    sources = [x["server_progid"] for x in data if x["server_progid"] and x["server_progid"] != "Unknown"]
    return sorted(list(set(sources)))

def get_unique_plants(data, selected_source):
    """Plants filtered by selected source"""
    filtered = data
    if selected_source:
        filtered = [x for x in data if x["server_progid"] == selected_source]
    plants = [x["plant"] for x in filtered]
    return sorted(list(set(plants)))

def get_areas_for_plant(data, selected_source, selected_plant):
    """Areas filtered by source AND plant"""
    filtered = data
    if selected_source:
        filtered = [x for x in filtered if x["server_progid"] == selected_source]
    if selected_plant:
        filtered = [x for x in filtered if x["plant"] == selected_plant]
    areas = [x["area"] for x in filtered]
    return sorted(list(set(areas)))

# Test scenarios
print("=" * 60)
print("SCENARIO 1: No source selected (show all)")
print("=" * 60)
sources = get_unique_sources(areasData)
plants = get_unique_plants(areasData, "")
print(f"Available Sources: {sources}")
print(f"Available Plants: {plants}")
print()

print("=" * 60)
print("SCENARIO 2: User selects 'PLC_GATEWAY_01'")
print("=" * 60)
selected_source = "PLC_GATEWAY_01"
sources = get_unique_sources(areasData)
plants = get_unique_plants(areasData, selected_source)
print(f"Available Sources: {sources}")
print(f"Available Plants (filtered by {selected_source}): {plants}")
print(f"✅ EXPECTED: ['Plant2']")
print(f"✅ RESULT: {plants}")
print(f"✅ PASS: {plants == ['Plant2']}")
print()

print("=" * 60)
print("SCENARIO 3: User selects 'PLC_GATEWAY_01' + 'Plant2'")
print("=" * 60)
selected_source = "PLC_GATEWAY_01"
selected_plant = "Plant2"
sources = get_unique_sources(areasData)
plants = get_unique_plants(areasData, selected_source)
areas = get_areas_for_plant(areasData, selected_source, selected_plant)
print(f"Available Sources: {sources}")
print(f"Available Plants (filtered by {selected_source}): {plants}")
print(f"Available Areas (filtered by {selected_source} + {selected_plant}): {areas}")
print(f"✅ EXPECTED: ['Area3', 'Area4']")
print(f"✅ RESULT: {areas}")
print(f"✅ PASS: {areas == ['Area3', 'Area4']}")
print()

print("=" * 60)
print("SCENARIO 4: User selects 'Matrikon.OPC.Simulation.1'")
print("=" * 60)
selected_source = "Matrikon.OPC.Simulation.1"
sources = get_unique_sources(areasData)
plants = get_unique_plants(areasData, selected_source)
print(f"Available Sources: {sources}")
print(f"Available Plants (filtered by {selected_source}): {plants}")
print(f"✅ EXPECTED: ['Plant1']")
print(f"✅ RESULT: {plants}")
print(f"✅ PASS: {plants == ['Plant1']}")
