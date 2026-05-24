# PLC Gateway - Multi-Protocol Transport

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVER (PLC Gateway)                               │
│                                                                              │
│   PlcDataLoggingService (1000ms polling from PLCs)                          │
│                    ↓                                                         │
│   PlcTagValuesPoolService (shared cache)                                    │
│                    ↓                                                         │
│   MultiProtocolPublisherService                                             │
│                    ↓                                                         │
│      ┌─────────────┴─────────────┐                                          │
│      ↓                           ↓                                           │
│   MQTT Broker              REST API                                         │
│   (plc/all topic)         (/api/plc/values)                                 │
│      ↓                           ↓                                           │
└──────┼───────────────────────────┼──────────────────────────────────────────┘
       ↓                           ↓
═══════════════════════════════════════════════════════════════════════════════
                              NETWORK
═══════════════════════════════════════════════════════════════════════════════
       ↓                           ↓
┌──────┴───────────────────────────┴──────────────────────────────────────────┐
│                           CLIENT (HMI / Dashboard)                           │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                   CLIENT-SIDE FAILOVER LOGIC                         │   │
│   │                                                                       │   │
│   │   1. Try MQTT first (real-time push, lower latency)                 │   │
│   │   2. If MQTT fails → switch to REST API (polling)                   │   │
│   │   3. Periodically check if MQTT is back → switch back               │   │
│   │                                                                       │   │
│   │   Same data, different delivery - CLIENT CHOOSES!                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Why Failover is CLIENT-SIDE

| Server-Side Failover (WRONG) | Client-Side Failover (CORRECT) |
|------------------------------|--------------------------------|
| Server decides protocol | Client decides protocol |
| Complex server logic | Simple server - just broadcast |
| Single point of failure | Distributed resilience |
| Can't adapt to client needs | Each client chooses best |
| Server manages connections | Client manages connections |

## Server Configuration

```json
{
  "PlcGateway": {
    "Transport": {
      "Enabled": true,
      "PublishIntervalMs": 1000
    },
    "Mqtt": {
      "Enabled": true,
      "BrokerHost": "localhost",
      "BrokerPort": 1883,
      "ClientId": "PlcGateway_Server1",
      "TopicPrefix": "factory1",
      "QualityOfService": 1,
      "RetainMessages": true
    }
  }
}
```

## Data Availability

### REST API (Always Available)
```
GET /api/plc/values          → All tags from all PLCs
GET /api/plc/values/{plcId}  → Tags from specific PLC
GET /api/plc/stats           → Pool statistics
GET /api/plc/health          → Health check
```

### MQTT Topics (When Enabled)
```
{prefix}/plc/all             → All PLCs, all tags (bulk)
{prefix}/plc/{plcId}/bulk    → Single PLC, all tags
{prefix}/plc/{plcId}/tags/{tagName} → Individual tag
```

## Client Failover Example (JavaScript)

```javascript
class PlcClient {
    constructor(options) {
        this.mqttUrl = options.mqttUrl;      // ws://broker:9001
        this.restUrl = options.restUrl;       // http://server:5000
        this.useMqtt = true;
        this.mqttClient = null;
    }

    async connect() {
        // Try MQTT first
        if (await this.connectMqtt()) {
            console.log('Connected via MQTT');
            return;
        }
        
        // Fallback to REST polling
        console.log('MQTT failed, using REST API');
        this.useMqtt = false;
        this.startPolling();
    }

    async connectMqtt() {
        try {
            this.mqttClient = mqtt.connect(this.mqttUrl);
            
            return new Promise((resolve) => {
                this.mqttClient.on('connect', () => {
                    this.mqttClient.subscribe('plc/all');
                    resolve(true);
                });
                
                this.mqttClient.on('error', () => resolve(false));
                
                setTimeout(() => resolve(false), 5000);
            });
        } catch {
            return false;
        }
    }

    startPolling() {
        setInterval(async () => {
            try {
                const response = await fetch(`${this.restUrl}/api/plc/values`);
                const data = await response.json();
                this.onData(data.values);
                
                // Try MQTT again periodically
                if (!this.useMqtt && Math.random() < 0.1) {
                    if (await this.connectMqtt()) {
                        this.useMqtt = true;
                        this.stopPolling();
                    }
                }
            } catch (err) {
                console.error('REST API error:', err);
            }
        }, 1000);
    }

    onData(values) {
        // Handle incoming data
        console.log('Received', values.length, 'tags');
    }
}
```

## Client Failover Example (Python)

```python
import paho.mqtt.client as mqtt
import requests
import time
import threading

class PlcClient:
    def __init__(self, mqtt_host, mqtt_port, rest_url):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.rest_url = rest_url
        self.use_mqtt = True
        self.mqtt_client = None
        self.running = True
    
    def connect(self):
        # Try MQTT first
        if self._connect_mqtt():
            print("Connected via MQTT")
            return
        
        # Fallback to REST
        print("MQTT failed, using REST API")
        self.use_mqtt = False
        self._start_polling()
    
    def _connect_mqtt(self):
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_message = self._on_mqtt_message
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.mqtt_client.subscribe("plc/all")
            self.mqtt_client.loop_start()
            return True
        except Exception as e:
            print(f"MQTT connection failed: {e}")
            return False
    
    def _on_mqtt_message(self, client, userdata, msg):
        import json
        data = json.loads(msg.payload)
        self.on_data(data['values'])
    
    def _start_polling(self):
        def poll():
            while self.running and not self.use_mqtt:
                try:
                    response = requests.get(f"{self.rest_url}/api/plc/values")
                    data = response.json()
                    self.on_data(data['values'])
                except Exception as e:
                    print(f"REST error: {e}")
                time.sleep(1)
        
        threading.Thread(target=poll, daemon=True).start()
    
    def on_data(self, values):
        print(f"Received {len(values)} tags")

# Usage
client = PlcClient("localhost", 1883, "http://localhost:5000")
client.connect()
```

## Benefits of This Design

1. **No Data Loss** - Same data on both protocols
2. **Client Choice** - Each client picks best protocol for its needs
3. **Simple Server** - Just broadcast everywhere
4. **Resilient** - If one protocol fails, other still works
5. **Scalable** - Add more protocols without changing clients
6. **Flexible** - Different clients can use different protocols
