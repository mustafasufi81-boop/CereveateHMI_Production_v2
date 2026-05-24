# HMI Remote Connection Setup

## Quick Setup

### 1. Enable Remote Access on HMI PC (192.168.0.120)
```cmd
cd HMI
ADD_FIREWALL_RULE.bat (Run as Administrator)
```

### 2. Configure Remote C# Backend Connection
```cmd
cd HMI
CONFIGURE_REMOTE_BACKEND.bat
```
Enter the IP of the PC running C# OPC backend (e.g., `192.168.0.10`)

### 3. Start HMI
```cmd
START_HMI.bat
```

## Access URLs

**HMI Dashboard:**
- Local: http://localhost:6002
- Network: http://192.168.0.120:6002

**C# Backend (on OPC PC):**
- Should be running on: http://{OPC_PC_IP}:5001

## Troubleshooting

### "Failed to fetch OPC values" Error
**Cause:** HMI cannot connect to C# backend on remote PC

**Solutions:**
1. ✅ Verify C# backend is running on the OPC PC
2. ✅ Check `config.json` has correct backend IP:
   ```json
   "csharp_backend": {
     "host": "192.168.0.10",  // IP of OPC PC
     "port": 5001
   }
   ```
3. ✅ Ensure firewall allows port 5001 on OPC PC:
   ```cmd
   netsh advfirewall firewall add rule name="OPC Backend" dir=in action=allow protocol=TCP localport=5001
   ```
4. ✅ Test connection from HMI PC:
   ```cmd
   curl http://192.168.0.10:5001/api/opc/values
   ```

### CORS Errors
**Cause:** C# backend not allowing cross-origin requests

**Solution:** Ensure C# `Program.cs` has CORS enabled:
```csharp
builder.Services.AddCors(options => {
    options.AddDefaultPolicy(policy => {
        policy.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader();
    });
});

app.UseCors();
```

### Network Topology

```
┌─────────────────────────────────────┐
│ OPC PC (192.168.0.10)               │
│ - C# Backend: 0.0.0.0:5001          │
│ - OPC DA Server                     │
└─────────────────────────────────────┘
            │
            │ Network (192.168.0.x)
            │
┌─────────────────────────────────────┐
│ HMI PC (192.168.0.120)              │
│ - Python HMI: 0.0.0.0:6002          │
│ - PostgreSQL Database               │
└─────────────────────────────────────┘
            │
            │
┌─────────────────────────────────────┐
│ Remote Devices (tablets, phones)    │
│ - Access: http://192.168.0.120:6002│
└─────────────────────────────────────┘
```

## Configuration Files

**HMI/config.json:**
```json
{
  "csharp_backend": {
    "host": "192.168.0.10",  // ← Change this to OPC PC IP
    "port": 5001,
    "signalr_hub": "/opcHub"
  },
  "hmi_server": {
    "host": "0.0.0.0",       // ← Keep as 0.0.0.0 (all interfaces)
    "port": 6002,
    "debug": true
  },
  "database": {
    "host": "localhost",     // ← Keep as localhost if DB on same PC
    "port": 5432,
    "database": "Cereveate",
    "user": "cereveate",
    "password": "cereveate@222"
  }
}
```

## Testing Connection

### Test C# Backend from HMI PC:
```powershell
# Test if C# backend is reachable
Invoke-WebRequest -Uri "http://192.168.0.10:5001/api/opc/values" -UseBasicParsing

# Expected: JSON response with tags
```

### Test HMI from Remote Device:
```bash
# From tablet/phone browser
http://192.168.0.120:6002
```

## Helper Scripts

- `ADD_FIREWALL_RULE.bat` - Add Windows Firewall rule for port 6002
- `CONFIGURE_REMOTE_BACKEND.bat` - Update backend IP in config.json
- `START_HMI.bat` - Start HMI server with network URLs displayed
