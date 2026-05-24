# OPC DA Web Browser - REST API Documentation

## Base URL
`http://localhost:5500/api/opc`

## Authentication
Currently no authentication required. Add authentication for production use.

## Endpoints

### 1. List OPC Servers
**GET** `/api/opc/servers`

Discovers all available OPC DA servers on the system.

**Response:**
```json
{
  "success": true,
  "servers": [
    "Matrikon.OPC.Simulation.1",
    "Kepware.KEPServerEX.V6",
    "MCS.OPCServer.1"
  ],
  "count": 3,
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 2. Get Connection Status
**GET** `/api/opc/status`

Returns current connection status.

**Response:**
```json
{
  "success": true,
  "isConnected": true,
  "currentServer": "Matrikon.OPC.Simulation.1",
  "monitoredTagCount": 6,
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 3. Connect to Server
**POST** `/api/opc/connect`

Connects to an OPC DA server.

**Request Body:**
```json
{
  "serverProgID": "Matrikon.OPC.Simulation.1"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Connected to Matrikon.OPC.Simulation.1",
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 4. Disconnect from Server
**POST** `/api/opc/disconnect`

Disconnects from current OPC server.

**Response:**
```json
{
  "success": true,
  "message": "Disconnected successfully",
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 5. Browse Tags
**GET** `/api/opc/tags`

Returns all available tags from the connected server.

**Response:**
```json
{
  "success": true,
  "tags": [
    {
      "name": "Random.Int4",
      "itemID": "Random.Int4",
      "isFolder": false,
      "path": "",
      "dataType": "Int32"
    },
    {
      "name": "Random.Real8",
      "itemID": "Random.Real8",
      "isFolder": false,
      "path": "",
      "dataType": "Double"
    }
  ],
  "count": 2,
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 6. Get All Tag Values
**GET** `/api/opc/values`

Returns current values of all monitored tags.

**Response:**
```json
{
  "success": true,
  "values": [
    {
      "itemID": "Random.Int4",
      "displayName": "Random.Int4",
      "value": "12345",
      "quality": "GOOD",
      "timestamp": "2025-11-14T01:45:00Z",
      "dataType": "Int32"
    }
  ],
  "count": 1,
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 7. Get Single Tag Value
**GET** `/api/opc/values/{itemID}`

Returns current value of a specific tag.

**Example:** `/api/opc/values/Random.Int4`

**Response:**
```json
{
  "success": true,
  "value": {
    "itemID": "Random.Int4",
    "displayName": "Random.Int4",
    "value": "12345",
    "quality": "GOOD",
    "timestamp": "2025-11-14T01:45:00Z",
    "dataType": "Int32"
  },
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 8. Add Tag to Monitoring
**POST** `/api/opc/monitor`

Adds a tag to the monitoring list.

**Request Body:**
```json
{
  "itemID": "Random.Int4",
  "displayName": "Random Integer"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Added 'Random Integer' to monitoring",
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 9. Remove Tag from Monitoring
**DELETE** `/api/opc/monitor/{itemID}`

Removes a tag from monitoring.

**Example:** `/api/opc/monitor/Random.Int4`

**Response:**
```json
{
  "success": true,
  "message": "Removed 'Random.Int4' from monitoring",
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 10. Get Trend Data
**GET** `/api/opc/trend/{itemID}?hours={hours}`

Returns historical trend data for a tag.

**Parameters:**
- `itemID` - Tag identifier (URL encoded)
- `hours` - Time range in hours (default: 1, max: 720)

**Example:** `/api/opc/trend/Random.Int4?hours=24`

**Response:**
```json
{
  "success": true,
  "itemID": "Random.Int4",
  "startTime": "2025-11-13T01:45:00Z",
  "endTime": "2025-11-14T01:45:00Z",
  "dataPoints": [
    {
      "timestamp": "2025-11-14T01:45:00Z",
      "value": "12345",
      "quality": "GOOD",
      "numericValue": 12345.0
    }
  ],
  "count": 1440,
  "timestamp": "2025-11-14T01:45:00Z"
}
```

### 11. Get Trend Statistics
**GET** `/api/opc/trend/{itemID}/stats?hours={hours}`

Returns statistical analysis of trend data.

**Example:** `/api/opc/trend/Random.Int4/stats?hours=24`

**Response:**
```json
{
  "success": true,
  "itemID": "Random.Int4",
  "startTime": "2025-11-13T01:45:00Z",
  "endTime": "2025-11-14T01:45:00Z",
  "stats": {
    "count": 1440,
    "min": 0.0,
    "max": 32767.0,
    "average": 16384.5,
    "firstValue": "12345",
    "lastValue": "23456"
  },
  "timestamp": "2025-11-14T01:45:00Z"
}
```

## Error Responses

All endpoints return error responses in this format:

```json
{
  "success": false,
  "error": "Error message here"
}
```

## CORS

CORS is enabled for all origins. Configure appropriately for production.

## Usage Examples

### Python
```python
import requests

# Discover servers
response = requests.get('http://192.168.1.38:5500/api/opc/servers')
servers = response.json()

# Connect to server
requests.post('http://192.168.1.38:5500/api/opc/connect', 
              json={'serverProgID': 'Matrikon.OPC.Simulation.1'})

# Get tag values
values = requests.get('http://192.168.1.38:5500/api/opc/values').json()
print(values)
```

### JavaScript
```javascript
// Fetch tag values
fetch('http://192.168.1.38:5500/api/opc/values')
  .then(response => response.json())
  .then(data => console.log(data.values));

// Get trend data
fetch('http://192.168.1.38:5500/api/opc/trend/Random.Int4?hours=24')
  .then(response => response.json())
  .then(data => console.log(data.dataPoints));
```

### cURL
```bash
# List servers
curl http://192.168.1.38:5500/api/opc/servers

# Connect to server
curl -X POST http://192.168.1.38:5500/api/opc/connect \
  -H "Content-Type: application/json" \
  -d '{"serverProgID":"Matrikon.OPC.Simulation.1"}'

# Get trend data
curl "http://192.168.1.38:5500/api/opc/trend/Random.Int4?hours=1"
```
