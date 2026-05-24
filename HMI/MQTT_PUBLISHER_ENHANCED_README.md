# Enhanced MQTT Test Publisher with Turbine Data & Alarms

## Overview
The enhanced `test_mqtt_publisher_from_db.py` now includes **realistic turbine operational patterns** with **automatic alarm generation** at WARNING and CRITICAL levels.

## 🎯 Key Features

### 1. **Realistic Turbine Data Simulation**
- **Smooth Trending**: Values change gradually with configurable trend rates
- **Parameter Profiles**: Specialized behavior for different sensor types:
  - **Speed (rpm)**: 1450-1550 normal, ±100 warning, ±150 critical
  - **Temperature (°C)**: 60-85 normal, ±25 warning, ±40 critical
  - **Pressure (bar)**: 8-12 normal, ±1 warning, ±2 critical
  - **Vibration (mm/s)**: 0.5-2.5 normal, 4.5 warning, 7.0 critical
  - **Flow (m³/h)**: 100-200 normal, ±20 warning, ±40 critical
  - **Power (kW)**: 800-1200 normal, ±100 warning, ±200 critical

### 2. **Intelligent Alarm Generation**
- **WARNING Level**: Values exceed normal operating range but not dangerous
- **CRITICAL Level**: Values reach dangerous thresholds requiring immediate action
- **Alarm Persistence**: Alarms remain active for 10-20 cycles before auto-recovery
- **Periodic Simulation**: Alarms triggered every 30-60 seconds for testing
- **Dedicated Alarm Topic**: `turbine/alarms` for centralized alarm monitoring

### 3. **Alarm Message Structure**
```json
{
  "timestamp": "2026-01-27T11:45:30.123Z",
  "alarmId": "ALM_Cooling_FAN_SPEED_1737975930",
  "tagName": "Cooling_FAN_SPEED",
  "plcName": "PLC_001",
  "severity": "CRITICAL",
  "message": "Cooling_FAN_SPEED: Value 1680.50 exceeds CRITICAL HIGH limit 1650",
  "value": 1680.5,
  "state": "ACTIVE",
  "acknowledged": false
}
```

### 4. **Enhanced Data Format**
Each tag value now includes:
- `alarmLevel`: "NORMAL", "WARNING", or "CRITICAL"
- `unit`: Engineering unit from database
- Realistic trending with noise simulation
- Quality indicators (Good/Bad)

## 🚀 Usage

### Basic Run
```powershell
cd C:\Shakil\DJangoProjects\NEW_HMI\HMI
python test_mqtt_publisher_from_db.py
```

### Output Example
```
🚀 DB-Based MQTT Test Publisher with ALARM SIMULATION
================================================================================
Features:
  ✓ Realistic turbine data trending
  ✓ WARNING and CRITICAL alarm generation
  ✓ Automatic alarm recovery
  ✓ Dedicated alarm topic: turbine/alarms
================================================================================

✅ Connected to MQTT broker: 127.0.0.1:1883

✅ Found 5 active MQTT topics:
  📍 turbine/sensors -> PLC: PLC_001 (20 tags)

================================================================================
📤 Starting MQTT test publisher with ALARM GENERATION
   Publishing every 1s
   Alarm Topic: turbine/alarms
================================================================================

[11:45:30.123] 📤 turbine/sensors  #0001 | 4520b | 20 tags | ⚠️  WARNING:1
     ───────────────────────────────────────────────────────────────────────────
     ⚠️  WARNING  | Cooling_FAN_SPEED          = 1605.3
     ───────────────────────────────────────────────────────────────────────────

[11:45:31.456] 📤 turbine/sensors  #0002 | 4535b | 20 tags | 🔴 CRITICAL:1
     ───────────────────────────────────────────────────────────────────────────
     🔴 CRITICAL | Boiler_Inlet_Temp          = 102.8
     ───────────────────────────────────────────────────────────────────────────
```

## 📊 Alarm Thresholds by Parameter Type

| Parameter Type | Normal Range | Warning Range | Critical Range |
|----------------|--------------|---------------|----------------|
| **Speed (rpm)** | 1450-1550 | 1400-1600 | 1350-1650 |
| **Temperature (°C)** | 60-85 | 50-90 | 40-100 |
| **Pressure (bar)** | 8-12 | 7-13 | 6-14.5 |
| **Vibration (mm/s)** | 0.5-2.5 | 0-4.5 | 0-7.0 |
| **Flow (m³/h)** | 100-200 | 80-220 | 60-250 |
| **Power (kW)** | 800-1200 | 700-1300 | 600-1400 |

## 🔧 Configuration

### Adjust Alarm Simulation Frequency
Edit the script:
```python
# Line ~280: Change alarm occurrence interval
if self.cycle_count % random.randint(30, 60) == 0:
# Change to (10, 20) for more frequent alarms
```

### Disable Automatic Alarm Simulation
```python
# Line ~153
self.alarm_simulation_mode = False  # Set to False
```

### Modify Publish Interval
```python
# Line 28
PUBLISH_INTERVAL = 1  # Change to desired seconds
```

## 📈 Trending Behavior

The simulator creates realistic industrial trends:
- **Inertia**: Values don't jump instantly, they trend smoothly
- **Noise**: Small random fluctuations simulate sensor noise
- **Recovery**: After alarm conditions, values trend back to normal range
- **Oscillation**: Values naturally oscillate within normal range

## 🎨 Visual Indicators

Console output uses:
- 🔴 **Red Circle**: CRITICAL alarms
- ⚠️ **Warning Sign**: WARNING alarms
- ✅ **Green Check**: Normal status
- 📤 **Outbox**: Published messages

## 🧪 Testing Alarm Responses

1. **Start the Publisher**: Runs continuously with alarm simulation
2. **Watch for Alarms**: WARNING and CRITICAL alarms appear periodically
3. **Subscribe to Alarm Topic**:
   ```bash
   mosquitto_sub -h 127.0.0.1 -t "turbine/alarms" -v
   ```
4. **Monitor HMI Response**: Check how your HMI displays and handles alarms

## 📝 Database Requirements

Ensure your database has:
- Active topics in `historian_raw.mqtt_topic_config`
- Tags in `historian_meta.tag_master` with:
  - `tag_name` matching turbine parameters
  - `eng_unit` for proper display
  - `enabled = true`

## 🔄 Auto-Recovery Feature

Alarms automatically recover after 10-20 cycles:
- Simulates operator intervention
- Prevents alarm flooding
- Tests alarm clearing logic in HMI

## 💡 Tips

1. **For Development**: Set `PUBLISH_INTERVAL = 2` to slow down for easier debugging
2. **For Load Testing**: Set `PUBLISH_INTERVAL = 0.5` for high-frequency data
3. **For Alarm Testing**: Monitor the `turbine/alarms` topic separately
4. **Real Patterns**: The trending simulates real turbine startup, steady-state, and shutdown

## 🐛 Troubleshooting

**No Alarms Appearing?**
- Check `self.alarm_simulation_mode = True` (line 153)
- Verify cycle count is incrementing
- Ensure tags match turbine parameter patterns

**Values Not Trending?**
- Check that tags have appropriate names (speed, temp, pressure, etc.)
- Verify `tag_states` dictionary is being populated

**MQTT Connection Issues?**
- Ensure Mosquitto broker is running
- Check `MQTT_BROKER` and `MQTT_PORT` settings
- Verify network connectivity

---

## 🚦 Next Steps

1. **Integrate with HMI**: Display alarms in trend charts with color coding
2. **Add Alarm Acknowledgment**: Subscribe to alarm ACK topic
3. **Historical Alarms**: Store alarm events in database
4. **Alarm Filtering**: Implement priority-based alarm management
5. **Email Notifications**: Send critical alarms to operators

---

**Author**: Enhanced for Industrial HMI Testing  
**Version**: 2.0 with Alarm Simulation  
**Last Updated**: January 27, 2026
