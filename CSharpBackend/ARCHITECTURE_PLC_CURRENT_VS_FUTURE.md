# PLC Gateway Architecture: Current vs Future State

**Document Version:** 2.0  
**Date:** January 2026  
**Scope:** PLC Gateway Module Only  
**Related Document:** `ARCHITECTURE_OPC_CURRENT_VS_FUTURE.md` (OPC DA Module)

---

## 0. Complete PLC Gateway Workflow (Future State)

### 0.1 End-to-End Data Flow Diagram

```
════════════════════════════════════════════════════════════════════════════════════════════════════════
                            PLC GATEWAY - COMPLETE FUTURE WORKFLOW
════════════════════════════════════════════════════════════════════════════════════════════════════════

                         ╔══════════════════════════════════════════════════════════════╗
                         ║           PLANT FLOOR / EDGE DEVICE (PLC Gateway)            ║
                         ╚══════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           PLCs (DATA SOURCES)                                        │
│                                                                                                      │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐            │
│   │ SIEMENS S7-1500 │   │ ALLEN-BRADLEY   │   │ MODBUS TCP      │   │ OMRON NJ/NX     │            │
│   │ Protocol: S7    │   │ Protocol: EIP   │   │ Protocol: Modbus│   │ Protocol: FINS  │            │
│   │ 192.168.1.10    │   │ 192.168.1.11    │   │ 192.168.1.12    │   │ 192.168.1.13    │            │
│   │                 │   │                 │   │                 │   │                 │            │
│   │ DB1.DBD0 Motor  │   │ Program:Main    │   │ 40001-40010     │   │ D0-D100         │            │
│   │ DB1.DBD4 Temp   │   │ Tag: Speed      │   │ Holding Regs    │   │ Data Memory     │            │
│   └────────┬────────┘   └────────┬────────┘   └────────┬────────┘   └────────┬────────┘            │
│            │                     │                     │                     │                      │
│            └─────────────────────┴──────────┬──────────┴─────────────────────┘                      │
│                                             ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                           DRIVER FACTORY (PlcDriverFactory.cs)                               │   │
│   │                                                                                              │   │
│   │   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐               │   │
│   │   │SiemensS7Driver│  │RockwellDriver │  │ModbusTcpDriver│  │ OmronDriver   │               │   │
│   │   │   (S7.Net)    │  │  (libplctag)  │  │   (NModbus)   │  │  (FINS TCP)   │               │   │
│   │   └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘               │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             │ ReadTagValues() every PollingIntervalMs
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 GATEWAY MANAGER LAYER                                                │
│                                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         PlcGatewayManager.cs (Orchestrator)                                  │   │
│   │                                                                                              │   │
│   │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │   │
│   │   │   WORKER A      │  │   WORKER B      │  │   WORKER C      │  │   WORKER D      │        │   │
│   │   │  PLC001 (S7)    │  │  PLC002 (AB)    │  │  PLC003 (Modbus)│  │  PLC004 (Omron) │        │   │
│   │   │  poll: 100ms    │  │  poll: 500ms    │  │  poll: 1000ms   │  │  poll: 200ms    │        │   │
│   │   │  ISOLATED TASK  │  │  ISOLATED TASK  │  │  ISOLATED TASK  │  │  ISOLATED TASK  │        │   │
│   │   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘        │   │
│   │            │                    │                    │                    │                 │   │
│   │            └────────────────────┴─────────┬──────────┴────────────────────┘                 │   │
│   │                                           ▼                                                  │   │
│   │   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │   │
│   │   │               PlcTagValuesPoolService.cs (SHARED CACHE - Thread Safe)               │   │   │
│   │   │                                                                                      │   │   │
│   │   │   ConcurrentDictionary<string, PlcTagValue>                                         │   │   │
│   │   │   ┌─────────────────────────────────────────────────────────────────────────────┐   │   │   │
│   │   │   │ "PLC001:Motor_Speed"  → {Value: 1750.5, Quality: Good, Timestamp: 10:30:01} │   │   │   │
│   │   │   │ "PLC001:Temperature"  → {Value: 65.2,   Quality: Good, Timestamp: 10:30:01} │   │   │   │
│   │   │   │ "PLC002:Pressure"     → {Value: 45.8,   Quality: Good, Timestamp: 10:30:01} │   │   │   │
│   │   │   │ "PLC003:Valve_Status" → {Value: true,   Quality: Good, Timestamp: 10:30:01} │   │   │   │
│   │   │   └─────────────────────────────────────────────────────────────────────────────┘   │   │   │
│   │   └─────────────────────────────────────────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             │ Pool updated → triggers publishing
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        LOCAL LOGGING ENGINE (CONFIGURABLE MODE)                                      │
│                                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                    PlcDataLoggingService.cs (UPDATED - MODE SELECTION)                       │   │
│   │                                                                                              │   │
│   │   logging-config.json: { "LocalLoggingMode": "Parquet" | "PostgreSQL" }                     │   │
│   │                                                                                              │   │
│   │   1. Generate batch_ref = ddmmyyhhmmss (e.g., "200126103001")  ← EVERY SECOND              │   │
│   │   2. Read values from PlcTagValuesPoolService                                               │   │
│   │   3. Store locally based on mode:                                                           │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                             │                                                        │
│            ┌────────────────────────────────┴────────────────────────────────┐                      │
│            ▼                                                                  ▼                      │
│   ┌─────────────────────────────────────────────┐   ┌─────────────────────────────────────────────┐ │
│   │           MODE A: PARQUET FILES             │   │          MODE B: POSTGRESQL                 │ │
│   │                                             │   │                                             │ │
│   │   Location: D:\PlcLogs\Data\{date}\         │   │   Database: plc_edge.buffer_data            │ │
│   │   Naming: {ddmmyy}_{hhmmss}_{seq}.parquet   │   │   batch_id: {ddmmyyhhmmss} VARCHAR(12)      │ │
│   │   Example: 200126_103000_001.parquet        │   │   Example: 200126103001, 200126103002       │ │
│   │   Content: Multiple MQTT batches per file   │   │   One row per tag per batch_ref            │ │
│   │   Cleanup: 30 days OR 10GB total            │   │   Cleanup: 7 days retention                 │ │
│   │   Recovery: Central requests by batch_ref   │   │   Recovery: Central requests by batch_ref   │ │
│   │             → read file → filter batch      │   │             → SELECT WHERE batch_id = ?     │ │
│   └─────────────────────────────────────────────┘   └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             │ 4. After local storage, publish to transports
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          TRANSPORT LAYER (MultiProtocolPublisherService.cs)                          │
│                                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                        SAME DATA → ALL ENABLED PROTOCOLS SIMULTANEOUSLY                      │   │
│   │                                                                                              │   │
│   │   PlcTagValuesPoolService.GetAllValues() + batch_ref                                        │   │
│   │                          │                                                                   │   │
│   │         ┌────────────────┼────────────────┬────────────────┐                                │   │
│   │         ▼                ▼                ▼                ▼                                │   │
│   │   ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐                         │   │
│   │   │   MQTT    │    │  REST API │    │ Local TCP │    │  SignalR  │                         │   │
│   │   │ Publisher │    │ /api/plc/ │    │ Port 5050 │    │  (future) │                         │   │
│   │   │           │    │  values   │    │ JSON push │    │           │                         │   │
│   │   └─────┬─────┘    └───────────┘    └───────────┘    └───────────┘                         │   │
│   │         │                                                                                    │   │
│   │         │ QoS 1 (At-least-once)                                                             │   │
│   │         │ Topic: plc/{plcId}/tags                                                           │   │
│   └─────────┼───────────────────────────────────────────────────────────────────────────────────┘   │
│             │                                                                                        │
│             ▼                                                                                        │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              MQTT MESSAGE FORMAT                                             │   │
│   │                                                                                              │   │
│   │   {                                                                                          │   │
│   │     "gateway_id": "PLC_GW_01",                                                              │   │
│   │     "plc_id": "PLC001",                                                                     │   │
│   │     "timestamp": "2026-01-20T10:30:01.123Z",                                                │   │
│   │     "batch_ref": "200126103001",                ← UNIQUE IDENTIFIER (every second)         │   │
│   │     "parquet_file": "200126_103000_001.parquet", ← Only for Parquet mode                   │   │
│   │     "local_logging_mode": "Parquet",                                                        │   │
│   │     "tag_count": 25,                                                                        │   │
│   │     "tags": [                                                                               │   │
│   │       {"tag_id": "Motor_Speed", "value": 1750.5, "quality": "Good", "timestamp": "..."},   │   │
│   │       {"tag_id": "Temperature", "value": 65.2, "quality": "Good", "timestamp": "..."}      │   │
│   │     ]                                                                                       │   │
│   │   }                                                                                          │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             │ MQTT over TCP/TLS (Network Boundary)
                                             ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════
                                       NETWORK BOUNDARY
═══════════════════════════════════════════════════════════════════════════════════════════════════════
                                             │
                                             ▼
                         ╔══════════════════════════════════════════════════════════════╗
                         ║                DATA CENTER / CLOUD (Central Server)          ║
                         ╚══════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            CENTRAL MQTT SUBSCRIBER (MqttSubscriberService.cs)                        │
│                                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                    Subscribe: plc/+/tags, opc/+/tags (wildcard for all gateways)            │   │
│   │                                                                                              │   │
│   │   FOR EACH MESSAGE:                                                                          │   │
│   │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐                         │   │
│   │   │  1. Parse JSON  │───▶│ 2. Track batch  │───▶│ 3. Rate Control │                         │   │
│   │   │  Extract batch  │    │ Insert into     │    │ Deadband check  │                         │   │
│   │   │  _ref + tags    │    │ batch_tracking  │    │ Interval check  │                         │   │
│   │   └─────────────────┘    └─────────────────┘    └────────┬────────┘                         │   │
│   │                                                          │                                   │   │
│   │                                              ┌───────────┴───────────┐                      │   │
│   │                                              ▼                       ▼                      │   │
│   │                                        ┌──────────┐           ┌──────────┐                  │   │
│   │                                        │  WRITE   │           │  FILTER  │                  │   │
│   │                                        │ (changed)│           │ (no chg) │                  │   │
│   │                                        └────┬─────┘           └──────────┘                  │   │
│   │                                             │                                                │   │
│   │                                             ▼                                                │   │
│   │   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │   │
│   │   │                     BATCH BUFFER (accumulate for bulk insert)                        │   │   │
│   │   │                     Flush: every 100 rows OR every 1000ms                            │   │   │
│   │   └─────────────────────────────────────────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                             │                                                        │
│                                             ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                    POSTGRESQL (Central)                                      │   │
│   │                                                                                              │   │
│   │   historian_raw.historian_timeseries (UNIFIED TABLE - OPC + PLC)                            │   │
│   │   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │   │
│   │   │ time       | tag_id            | value  | quality | source_type | gateway_id | batch│   │   │
│   │   │ ───────────┼───────────────────┼────────┼─────────┼─────────────┼────────────┼──────│   │   │
│   │   │ 10:30:01   | PLC001:Motor_Speed| 1750.5 | Good    | PLC         | PLC_GW_01  | 2001.│   │   │
│   │   │ 10:30:01   | PLC001:Temperature| 65.2   | Good    | PLC         | PLC_GW_01  | 2001.│   │   │
│   │   │ 10:30:02   | PLC002:Pressure   | 46.1   | Good    | PLC         | PLC_GW_01  | 2001.│   │   │
│   │   └─────────────────────────────────────────────────────────────────────────────────────┘   │   │
│   │                                                                                              │   │
│   │   historian_admin.batch_tracking (TRACKS ALL RECEIVED BATCHES)                              │   │
│   │   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │   │
│   │   │ gateway_id | batch_ref     | parquet_file              | received_at  | status     │   │   │
│   │   │ ───────────┼───────────────┼───────────────────────────┼──────────────┼────────────│   │   │
│   │   │ PLC_GW_01  | 200126103001  | 200126_103000_001.parquet | 10:30:01     | RECEIVED   │   │   │
│   │   │ PLC_GW_01  | 200126103002  | 200126_103000_001.parquet | 10:30:02     | RECEIVED   │   │   │
│   │   │ PLC_GW_01  | 200126103003  | NULL (PostgreSQL mode)    | 10:30:03     | RECEIVED   │   │   │
│   │   └─────────────────────────────────────────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             │ Periodic gap detection (every 5 min)
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              BATCH RECOVERY SERVICE (BatchRecoveryService.cs)                        │
│                                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │   1. DETECT GAPS: SELECT detect_missing_batches('PLC_GW_01', last_24h)                      │   │
│   │      Returns: ['200126103045', '200126104512', ...]  (missing batch_refs)                   │   │
│   │                                                                                              │   │
│   │   2. REQUEST RECOVERY: FOR EACH missing_batch_ref:                                          │   │
│   │      GET http://plc-gw-01:5000/api/recovery/batch/200126103045                              │   │
│   │                                                                                              │   │
│   │   3. GATEWAY RESPONDS: (based on local storage mode)                                        │   │
│   │      Parquet: Read file → filter by batch_ref → return JSON                                │   │
│   │      PostgreSQL: SELECT * FROM buffer_data WHERE batch_id = '200126103045'                 │   │
│   │                                                                                              │   │
│   │   4. CENTRAL INSERTS: Missing data into historian_timeseries                               │   │
│   │      UPDATE recovery_requests SET status = 'RECOVERED'                                      │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════════════════════
                                          LEGEND
═══════════════════════════════════════════════════════════════════════════════════════════════════════
│ ✅ EXISTING   │ Already implemented, no changes needed                                              │
│ 🔧 UPDATED    │ Existing code modified for dual-mode local logging + batch_ref                     │
│ 🆕 NEW        │ New component to be created                                                         │
│ ⚠️ REMOVED    │ PlcHistorianIngestService.cs - replaced by Central Subscriber                      │
│ →             │ Data flow direction                                                                  │
│ batch_ref     │ Unique identifier: ddmmyyhhmmss (e.g., 200126103001 = 20 Jan 26, 10:30:01)          │
═══════════════════════════════════════════════════════════════════════════════════════════════════════
```

---

## 1. Executive Summary

### PLC Gateway Current State
```
┌─────────────────────────────────────────────────────────────────┐
│                    PLC GATEWAY (CURRENT)                        │
│                                                                 │
│  ✅ ALREADY HAS: MQTT Publisher + REST API + Local TCP         │
│  ⚠️  PROBLEM: Direct DB writes embedded in same service        │
│                                                                 │
│  PLCs → PlcGateway → [Pool] → MQTT/REST/TCP (ALREADY WORKS!)   │
│                        ↓                                        │
│              PlcHistorianIngestService (EMBEDDED DB WRITE)      │
│                        ↓                                        │
│                   PostgreSQL                                    │
└─────────────────────────────────────────────────────────────────┘
```

### PLC Gateway Future State
```
┌─────────────────────────────────────────────────────────────────┐
│                    PLC GATEWAY (FUTURE)                         │
│                                                                 │
│  ✅ DECOUPLED: Gateway ONLY polls + publishes                   │
│  ✅ SEPARATE: Central Subscriber handles DB writes              │
│                                                                 │
│  PLCs → PlcGateway → [Pool] → MQTT/REST/TCP ──→ Subscribers    │
│                                                                 │
│  [Gateway runs on Plant Floor / Edge Device]                   │
│                                   ↓                             │
│                        Central MQTT Subscriber                  │
│                                   ↓                             │
│                             PostgreSQL                          │
│                                                                 │
│  [Database runs in Central Data Center / Cloud]                │
└─────────────────────────────────────────────────────────────────┘
```

### Key Difference
| Aspect | Current | Future |
|--------|---------|--------|
| DB Write Location | Gateway process | Separate subscriber |
| Deployment | Single machine | Distributed |
| Scaling | Vertical only | Horizontal |
| Failure Isolation | DB errors affect polling | Completely isolated |

---

## 2. Architecture Flow Diagrams

### 2.1 CURRENT Architecture Flow
```
════════════════════════════════════════════════════════════════════════════════
                         PLC GATEWAY - CURRENT STATE
════════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                    │
│                                                                             │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│   │ Siemens S7  │   │ Allen-Brad  │   │ Modbus TCP  │   │   Omron     │    │
│   │ PLC #1      │   │  PLC #2     │   │ Device #3   │   │  PLC #4     │    │
│   │ 192.168.1.10│   │ 192.168.1.11│   │ 192.168.1.12│   │ 192.168.1.13│    │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘    │
│          │                 │                 │                 │            │
│          └─────────────────┴────────┬────────┴─────────────────┘            │
│                                     ▼                                       │
│                            DRIVER FACTORY                                   │
│                    (SiemensS7Driver, RockwellDriver,                       │
│                     ModbusTcpDriver, OmronDriver)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GATEWAY MANAGER LAYER                               │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │                    PlcGatewayManager.cs                             │   │
│   │   ┌──────────────┬──────────────┬──────────────┬──────────────┐    │   │
│   │   │   Worker A   │   Worker B   │   Worker C   │   Worker D   │    │   │
│   │   │  (Siemens)   │  (Rockwell)  │   (Modbus)   │   (Omron)    │    │   │
│   │   │  Isolated!   │  Isolated!   │  Isolated!   │  Isolated!   │    │   │
│   │   └──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┘    │   │
│   │          │              │              │              │            │   │
│   │          └──────────────┴──────┬───────┴──────────────┘            │   │
│   └─────────────────────────────────┼──────────────────────────────────┘   │
│                                     ▼                                       │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │            PlcTagValuesPoolService.cs (SHARED CACHE)               │   │
│   │                                                                     │   │
│   │   Key: "PLC001:Motor_Speed" → {Value: 1750.5, Quality: Good, TS}  │   │
│   │   Key: "PLC002:Pressure"    → {Value: 45.2, Quality: Good, TS}    │   │
│   │   Key: "PLC003:Valve_Open"  → {Value: true, Quality: Good, TS}    │   │
│   │                                                                     │   │
│   │   ConcurrentDictionary - Thread-safe for parallel access           │   │
│   └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│  TRANSPORT LAYER      │ │   HISTORIAN LAYER     │ │   LOGGING LAYER       │
│  (MultiProtocol)      │ │   (DB Writes)         │ │   (Parquet)           │
│                       │ │                       │ │                       │
│  ┌─────────────────┐  │ │ ┌─────────────────┐   │ │ ┌─────────────────┐   │
│  │ MQTT Publisher  │  │ │ │  PlcHistorian   │   │ │ │  PlcDataLogging │   │
│  │ (To Broker)     │  │ │ │  IngestService  │   │ │ │  Service        │   │
│  └────────┬────────┘  │ │ │                 │   │ │ │                 │   │
│           │           │ │ │ Rate Control    │   │ │ │ 10MB Rotation   │   │
│  ┌────────┴────────┐  │ │ │ Deadband Check  │   │ │ │ SelectedTags    │   │
│  │ REST API        │  │ │ │ Batch Insert    │   │ │ │                 │   │
│  │ (PlcController) │  │ │ └────────┬────────┘   │ │ └────────┬────────┘   │
│  └────────┬────────┘  │ │          │            │ │          │            │
│           │           │ │          ▼            │ │          ▼            │
│  ┌────────┴────────┐  │ │ ┌─────────────────┐   │ │ ┌─────────────────┐   │
│  │ Local TCP       │  │ │ │   PostgreSQL    │   │ │ │  D:\PlcLogs\    │   │
│  │ (Port 5050)     │  │ │ │ plc_timeseries  │   │ │ │  *.parquet      │   │
│  └─────────────────┘  │ │ └─────────────────┘   │ │ └─────────────────┘   │
│                       │ │                       │ │                       │
│ ✅ ALREADY WORKING!   │ │ ⚠️ EMBEDDED (PROBLEM) │ │ ✅ RETAINED AS-IS     │
└───────────────────────┘ └───────────────────────┘ └───────────────────────┘

LEGEND:
════════════════════════════════════════════════════════════════════════════════
│ ✅ RETAINED │ Working well, keep as-is                                      │
│ ⚠️ EMBEDDED │ DB writes inside Gateway process - needs decoupling          │
│ → ARROW    │ Data flow direction                                            │
════════════════════════════════════════════════════════════════════════════════
```

### 2.2 FUTURE Architecture Flow
```
════════════════════════════════════════════════════════════════════════════════
                         PLC GATEWAY - FUTURE STATE
════════════════════════════════════════════════════════════════════════════════

                    ╔══════════════════════════════════════╗
                    ║     EDGE DEVICE / PLANT FLOOR        ║
                    ╚══════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                    │
│                                                                             │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│   │ Siemens S7  │   │ Allen-Brad  │   │ Modbus TCP  │   │   Omron     │    │
│   │ PLC #1      │   │  PLC #2     │   │ Device #3   │   │  PLC #4     │    │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘    │
│          └─────────────────┴────────┬────────┴─────────────────┘            │
│                                     ▼                                       │
│                            DRIVER FACTORY                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GATEWAY MANAGER LAYER                               │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │                    PlcGatewayManager.cs ✅ RETAINED                 │   │
│   │   ┌──────────────┬──────────────┬──────────────┬──────────────┐    │   │
│   │   │   Worker A   │   Worker B   │   Worker C   │   Worker D   │    │   │
│   │   │  (Siemens)   │  (Rockwell)  │   (Modbus)   │   (Omron)    │    │   │
│   │   └──────────────┴──────────────┴──────────────┴──────────────┘    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│   ┌─────────────────────────────────▼──────────────────────────────────┐   │
│   │          PlcTagValuesPoolService.cs ✅ RETAINED                     │   │
│   │   + PlcSampleBufferService.cs ✅ RETAINED (Multi-sample buffering) │   │
│   └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│  MQTT PUBLISHER       │ │   REST API            │ │   LOCAL TCP           │
│  ✅ ALREADY EXISTS    │ │   ✅ ALREADY EXISTS   │ │   ✅ ALREADY EXISTS   │
│                       │ │                       │ │                       │
│  MqttPublisher.cs     │ │   PlcController.cs    │ │ LocalTcpBroadcast.cs  │
│                       │ │                       │ │                       │
│  Topic: plc/{plcId}/  │ │   GET /api/plc/values │ │   Port 5050           │
│         tags          │ │   GET /api/plc/status │ │   JSON newline        │
│                       │ │                       │ │                       │
│  QoS 1 + Buffering    │ │   Pull-based polling  │ │   Push to clients     │
└───────────┬───────────┘ └───────────────────────┘ └───────────────────────┘
            │
            │ MQTT Messages (QoS 1)
            │ Topic: plc/{plcId}/tags
            │ Payload: {samples: [...], timestamp, quality}
            ▼
════════════════════════════════════════════════════════════════════════════════
                              NETWORK BOUNDARY
════════════════════════════════════════════════════════════════════════════════
            │
            │ MQTT over TCP/TLS
            ▼
                    ╔══════════════════════════════════════╗
                    ║     DATA CENTER / CLOUD              ║
                    ╚══════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────┐
│                     CENTRAL MQTT SUBSCRIBER 🆕 NEW                          │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │                    MqttSubscriberService.cs                         │   │
│   │                                                                     │   │
│   │   Subscribe: plc/+/tags, opc/+/tags                                │   │
│   │   (+ = wildcard for any plcId/serverId)                            │   │
│   │                                                                     │   │
│   │   ┌─────────────────┐    ┌─────────────────┐                       │   │
│   │   │ Message Parser  │───▶│ Rate Controller │                       │   │
│   │   │ (JSON decode)   │    │ (Deadband/Time) │                       │   │
│   │   └─────────────────┘    └────────┬────────┘                       │   │
│   │                                   │                                 │   │
│   │                    ┌──────────────┼──────────────┐                 │   │
│   │                    ▼              ▼              ▼                 │   │
│   │            ┌────────────┐  ┌────────────┐  ┌────────────┐         │   │
│   │            │   Batch    │  │   Spool    │  │   Alarm    │         │   │
│   │            │   Buffer   │  │   Manager  │  │   Engine   │         │   │
│   │            └─────┬──────┘  └─────┬──────┘  └─────┬──────┘         │   │
│   │                  │               │               │                 │   │
│   └──────────────────┼───────────────┼───────────────┼─────────────────┘   │
│                      │               │               │                     │
│                      ▼               ▼               ▼                     │
│   ┌─────────────────────────────────────────────────────────────────────┐ │
│   │                         PostgreSQL                                   │ │
│   │                                                                      │ │
│   │   historian_raw.historian_timeseries   (OPC + PLC unified)          │ │
│   │   historian_meta.alarm_events          (Alarms from both)           │ │
│   │                                                                      │ │
│   └─────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ⚠️ PlcHistorianIngestService.cs → REMOVED (replaced by central sub)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

LEGEND:
════════════════════════════════════════════════════════════════════════════════
│ ✅ RETAINED │ Existing code, keep as-is                                     │
│ 🆕 NEW      │ New component to be created                                   │
│ ⚠️ REMOVED  │ Will be deleted/disabled after migration                      │
════════════════════════════════════════════════════════════════════════════════
```

---

## 3. Module Inventory

### 3.1 Complete Module Status Table

| Module | File | Location | Status | Notes |
|--------|------|----------|--------|-------|
| **Gateway Manager** | `PlcGatewayManager.cs` | Services/PlcGateway/Services/ | ✅ RETAINED | Multi-PLC worker orchestration |
| **Driver Factory** | `PlcDriverFactory.cs` | Services/PlcGateway/Drivers/ | ✅ RETAINED | Creates protocol-specific drivers |
| **Siemens Driver** | `SiemensS7Driver.cs` | Services/PlcGateway/Drivers/ | ✅ RETAINED | S7.Net library |
| **Rockwell Driver** | `RockwellDriver.cs` | Services/PlcGateway/Drivers/ | ✅ RETAINED | libplctag library |
| **Modbus Driver** | `ModbusTcpDriver.cs` | Services/PlcGateway/Drivers/ | ✅ RETAINED | NModbus library |
| **Omron Driver** | `OmronDriver.cs` | Services/PlcGateway/Drivers/ | ✅ RETAINED | FINS TCP protocol |
| **ABB Driver** | `AbbDriver.cs` | Services/PlcGateway/Drivers/ | ✅ RETAINED | NModbus library |
| **Mitsubishi Driver** | `MitsubishiDriver.cs` | Services/PlcGateway/Drivers/ | ✅ RETAINED | NModbus library |
| **Tag Values Pool** | `PlcTagValuesPoolService.cs` | Services/PlcGateway/Services/ | ✅ RETAINED | Shared in-memory cache |
| **Sample Buffer** | `PlcSampleBufferService.cs` | Services/PlcGateway/Services/ | ✅ RETAINED | Multi-sample buffering |
| **Data Logging** | `PlcDataLoggingService.cs` | Services/PlcGateway/Services/ | ✅ RETAINED | Parquet file logging |
| **Config Loader** | `PlcConfigLoaderService.cs` | Services/PlcGateway/Services/ | ✅ RETAINED | Loads PLC configs from DB/JSON |
| **Config Persistence** | `PlcConfigPersistenceService.cs` | Services/PlcGateway/Services/ | ✅ RETAINED | Saves configs to JSON |
| **MQTT Publisher** | `MqttPublisher.cs` | Services/PlcGateway/Transport/ | ✅ RETAINED | TCP-based MQTT client |
| **Multi-Protocol Pub** | `MultiProtocolPublisherService.cs` | Services/PlcGateway/Transport/ | ✅ RETAINED | Broadcasts to all protocols |
| **Local TCP Broadcast** | `LocalTcpBroadcastService.cs` | Services/PlcGateway/Transport/ | ✅ RETAINED | Direct TCP broadcast |
| **REST API Controller** | `PlcController.cs` | Controllers/ | ✅ RETAINED | HTTP API for values |
| **Health Publisher** | `HealthPublisherService.cs` | Services/PlcGateway/Transport/ | ✅ RETAINED | Gateway health metrics |
| **Historian Ingest** | `PlcHistorianIngestService.cs` | Services/PlcGateway/Services/ | ⚠️ REMOVED | Replaced by central subscriber |
| **Central Subscriber** | `MqttSubscriberService.cs` | Services/CentralIngest/ | 🆕 NEW | Unified DB writer |

### 3.2 Transport Protocol Summary (All Already Exist!)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   PLC GATEWAY TRANSPORT LAYER (CURRENT)                     │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                MultiProtocolPublisherService.cs                      │   │
│  │                                                                      │   │
│  │   "Publish SAME DATA to ALL enabled protocols SIMULTANEOUSLY"       │   │
│  │   "Client chooses which protocol to consume"                        │   │
│  │                                                                      │   │
│  │   PlcTagValuesPoolService (shared cache)                            │   │
│  │                   ↓                                                  │   │
│  │   MultiProtocolPublisherService                                      │   │
│  │                   ↓                                                  │   │
│  │   ┌───────────────┼───────────────┐                                 │   │
│  │   ↓               ↓               ↓                                 │   │
│  │ MQTT          REST API       Local TCP                              │   │
│  │ (broker)      (/api/plc)     (port 5050)                            │   │
│  │   ↓               ↓               ↓                                 │   │
│  │ ═══════════════════════════════════════                             │   │
│  │        CLIENT CHOOSES ONE                                            │   │
│  │     (with failover to another)                                       │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ✅ THIS IS EXACTLY WHAT WE NEED! NO CHANGES REQUIRED!                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Module Descriptions

### 4.1 ✅ RETAINED: PlcGatewayManager

**File:** `Services/PlcGateway/Services/PlcGatewayManager.cs`  
**Lines:** 393  
**Status:** ✅ RETAINED - No changes needed

**Purpose:**
```
Manages multiple ISOLATED PLC workers

KEY PRINCIPLES:
1. Each PLC = One Worker = Complete Isolation
2. Workers run in parallel (Task per worker)
3. No shared connections or data
4. Add/Remove PLCs at runtime without affecting others
5. Same manufacturer PLCs work independently
6. Different manufacturers work together
```

**Key Methods:**
- `AddPlcAsync(config, tags)` - Add new PLC at runtime
- `RemovePlcAsync(plcId)` - Remove PLC without affecting others
- `GetWorkerStatus(plcId)` - Get status of specific worker
- `GetAllWorkerStatuses()` - Get status of all workers

**Why Retained:**
This component is protocol-agnostic - it manages workers regardless of whether data goes to DB directly or via MQTT. The isolation pattern is essential for reliability.

### 4.2 ✅ RETAINED: PlcTagValuesPoolService

**File:** `Services/PlcGateway/Services/PlcTagValuesPoolService.cs`  
**Lines:** ~150  
**Status:** ✅ RETAINED - No changes needed

**Purpose:**
```csharp
// Shared in-memory cache for ALL consumers
// Updated by PlcDataLoggingService every poll cycle

public class PlcTagValuesPoolService
{
    private readonly ConcurrentDictionary<string, PlcTagValue> _pool = new();
    
    // Write (from workers)
    public void UpdatePool(string plcId, Dictionary<string, PlcTagValue> values)
    
    // Read (from API, MQTT, Historian)
    public Dictionary<string, PlcTagValue> GetAllTagValues()
    public PlcTagValue? GetTagValue(string fullTagId)
}
```

**Consumers:**
1. `PlcController.cs` (REST API) - GET /api/plc/values
2. `MqttPublisher.cs` - Publishes to broker
3. `LocalTcpBroadcastService.cs` - Broadcasts to TCP clients
4. `PlcHistorianIngestService.cs` - Reads for DB writes (WILL BE REMOVED)

### 4.3 ✅ RETAINED: MqttPublisher

**File:** `Services/PlcGateway/Transport/MqttPublisher.cs`  
**Lines:** 601  
**Status:** ✅ RETAINED - Already exactly what we need

**Purpose:**
```csharp
/// MQTT Publisher - TCP-based client
/// 
/// KEY FEATURES:
/// - QoS 1 (At-least-once delivery)
/// - Auto-reconnect on disconnect
/// - Bulk mode: All PLCs in single topic
/// - Per-PLC mode: Separate topic per PLC
/// - Sample buffering support

public class MqttPublisher
{
    // Publish latest values (single sample per tag)
    public async Task PublishAsync(Dictionary<string, PlcTagValue> values, CancellationToken ct)
    
    // Publish with sample buffer (multiple samples per tag)
    public async Task PublishWithSamplesAsync(
        Dictionary<string, PlcTagSamples> tagSamples, 
        int intervalMs, 
        CancellationToken ct)
}
```

**Topic Structure:**
```
plc/{plcId}/tags
    └── Payload: {
          "plcId": "PLC001",
          "timestamp": "2024-12-09T10:30:00.123Z",
          "tags": [
            {"tagId": "Motor_Speed", "value": 1750.5, "quality": "Good"},
            {"tagId": "Pressure", "value": 45.2, "quality": "Good"}
          ]
        }
```

### 4.4 ✅ RETAINED: MultiProtocolPublisherService

**File:** `Services/PlcGateway/Transport/MultiProtocolPublisherService.cs`  
**Lines:** 226  
**Status:** ✅ RETAINED - Already broadcasts to all protocols

**Current Design:**
```csharp
/// Multi-Protocol Publisher Service (SERVER-SIDE):
/// - Reads from PlcTagValuesPoolService
/// - Publishes SAME DATA to ALL enabled protocols SIMULTANEOUSLY
/// - MQTT, REST API, WebSocket - all get the same data
/// - Client chooses which protocol to consume
/// - Client handles failover (not server)
```

**Why This Is Perfect:**
- Already broadcasts to MQTT (for remote subscribers)
- Already exposes REST API (for polling clients)
- Already broadcasts to Local TCP (for plant floor HMIs)
- No changes needed for decoupled architecture!

### 4.5 ✅ RETAINED: LocalTcpBroadcastService

**File:** `Services/PlcGateway/Transport/LocalTcpBroadcastService.cs`  
**Lines:** 328  
**Status:** ✅ RETAINED - Essential for plant floor

**Purpose:**
```
LOCAL TCP Broadcast Server - NO CLOUD, NO INTERNET, NO THIRD PARTY

PURPOSE:
- Broadcasts PLC data to clients on YOUR LOCAL NETWORK ONLY
- No external broker required (like Mosquitto)
- No data leaves your network
- Clients connect directly to this server

PORT: 5050 (configurable)
PROTOCOL: Newline-delimited JSON
```

**Why Retained:**
Plant floor HMIs need direct TCP access even if MQTT fails. This provides a fallback that doesn't depend on any external infrastructure.

### 4.6 ⚠️ REMOVED: PlcHistorianIngestService

**File:** `Services/PlcGateway/Services/PlcHistorianIngestService.cs`  
**Lines:** 354  
**Status:** ⚠️ REMOVED - Replaced by Central MQTT Subscriber

**Current Design (To Be Removed):**
```csharp
/// PLC Historian Ingest Service
/// 
/// - Reads from PlcTagValuesPoolService (NOT direct PLC reads)
/// - Applies rate control (deadband + interval)
/// - Writes to PostgreSQL plc_gateway.plc_timeseries

// PROBLEM: DB connection inside gateway process
// If DB fails, can affect gateway reliability
```

**Migration Path:**
1. Keep service running during transition
2. Deploy Central MQTT Subscriber
3. Verify data flowing through MQTT to DB
4. Disable PlcHistorianIngestService
5. Delete after confirmation

### 4.7 🆕 NEW: Central MQTT Subscriber

**File:** `Services/CentralIngest/MqttSubscriberService.cs`  
**Status:** 🆕 NEW - To be created

**Purpose:**
```csharp
/// Central MQTT Subscriber Service
/// 
/// SUBSCRIBES TO:
/// - plc/+/tags (all PLC gateways)
/// - opc/+/tags (all OPC gateways)
/// 
/// PROCESSES:
/// - Parse JSON messages
/// - Apply rate control (deadband/interval)
/// - Batch for efficiency
/// - Write to PostgreSQL
/// 
/// UNIFIED TABLE:
/// - historian_raw.historian_timeseries (both OPC and PLC)
/// - source_type column: 'OPC' or 'PLC'
```

---

## 5. Database Changes

### 5.1 Existing PLC Tables (RETAINED)

```sql
-- EXISTING: PLC Gateway Schema (RETAINED)
CREATE SCHEMA IF NOT EXISTS plc_gateway;

-- PLC Connections (RETAINED)
CREATE TABLE IF NOT EXISTS plc_gateway.plc_connections (
    id SERIAL PRIMARY KEY,
    plc_id VARCHAR(100) UNIQUE NOT NULL,
    plc_name VARCHAR(200),
    protocol VARCHAR(50) NOT NULL,  -- Siemens, Rockwell, Modbus, etc.
    ip_address VARCHAR(50) NOT NULL,
    port INTEGER,
    polling_interval_ms INTEGER DEFAULT 1000,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- PLC Tag Definitions (RETAINED)
CREATE TABLE IF NOT EXISTS plc_gateway.plc_tags (
    id SERIAL PRIMARY KEY,
    plc_id VARCHAR(100) REFERENCES plc_gateway.plc_connections(plc_id),
    tag_id VARCHAR(200) NOT NULL,
    tag_name VARCHAR(200),
    address VARCHAR(100),  -- e.g., "DB1.DBD0" for Siemens
    data_type VARCHAR(50),
    deadband_value DECIMAL(10,4) DEFAULT 0,
    db_logging_enabled BOOLEAN DEFAULT true,
    db_logging_interval_ms INTEGER DEFAULT 1000,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(plc_id, tag_id)
);
```

### 5.2 Migration to Unified Table

**Current:** Separate tables for OPC and PLC data
- `historian_raw.historian_timeseries` (OPC only)
- `plc_gateway.plc_timeseries` (PLC only)

**Future:** Single unified table
```sql
-- UNIFIED: Both OPC and PLC data in same table
ALTER TABLE historian_raw.historian_timeseries 
ADD COLUMN IF NOT EXISTS source_type VARCHAR(10) DEFAULT 'OPC';
-- Values: 'OPC', 'PLC'

ALTER TABLE historian_raw.historian_timeseries 
ADD COLUMN IF NOT EXISTS source_id VARCHAR(200);
-- For OPC: server_id (e.g., "Matrikon.OPC.Simulation.1")
-- For PLC: plc_id (e.g., "PLC001")

-- INDEX for source-based queries
CREATE INDEX IF NOT EXISTS idx_historian_source 
ON historian_raw.historian_timeseries (source_type, source_id, time DESC);
```

### 5.3 Tag Master Extensions

```sql
-- ADD columns for PLC tag mappings (if not exists)
ALTER TABLE historian_meta.tag_master
ADD COLUMN IF NOT EXISTS source_type VARCHAR(10) DEFAULT 'OPC',
ADD COLUMN IF NOT EXISTS source_id VARCHAR(200),
ADD COLUMN IF NOT EXISTS plc_address VARCHAR(100);

-- EXAMPLE: PLC tag in tag_master
INSERT INTO historian_meta.tag_master (
    tag_id, 
    tag_name, 
    source_type, 
    source_id,
    plc_address,
    data_type, 
    deadband_value, 
    enabled
) VALUES (
    'PLC001:Motor_Speed',
    'Motor Speed RPM',
    'PLC',
    'PLC001',
    'DB1.DBD0',
    'double',
    5.0,
    true
);
```

---

## 6. Configuration Comparison

### 6.1 Current Configuration (appsettings.json)

```json
{
  "PlcGateway": {
    "PollingIntervalMs": 1000,
    "ParquetWriteIntervalMs": 5000,
    "ParquetOutputPath": "D:\\PlcLogs\\Data",
    "EnableParquetLogging": false,
    
    "HistorianPollIntervalMs": 1000,
    "HistorianBatchSize": 100,
    "DefaultWriteIntervalMs": 1000,
    
    "Transport": {
      "Enabled": true,
      "PublishIntervalMs": 1000,
      "UseSampleBuffer": true
    },
    
    "Mqtt": {
      "Enabled": true,
      "BrokerHost": "localhost",
      "BrokerPort": 1883,
      "ClientId": "plc-gateway-01",
      "Username": "",
      "Password": "",
      "UseTls": false,
      "TopicPrefix": "plc"
    },
    
    "LocalBroadcast": {
      "Enabled": true,
      "Port": 5050,
      "IntervalMs": 1000,
      "BindAddress": "0.0.0.0"
    }
  }
}
```

### 6.2 Future Configuration (No changes needed!)

The existing configuration already supports decoupled operation:
- MQTT publishing is already configurable
- Local TCP broadcast provides plant floor fallback
- REST API always available

**Only addition:** Central subscriber configuration (in separate service)
```json
{
  "CentralSubscriber": {
    "MqttBrokerHost": "mqtt-broker.company.local",
    "MqttBrokerPort": 1883,
    "SubscribeTopics": ["plc/+/tags", "opc/+/tags"],
    "DatabaseConnectionString": "...",
    "BatchSize": 100,
    "BatchTimeoutMs": 1000
  }
}
```

---

## 7. Migration Strategy

### 7.1 Phase 1: Verify Existing MQTT (Week 1)

```
[ALREADY EXISTS - JUST VERIFY]

PLC Gateway                          MQTT Broker
    │                                     │
    │ ──── MQTT Publish (existing) ────▶  │
    │      plc/{plcId}/tags               │
    │                                     │
    └──── Direct DB Write (existing) ──▶ PostgreSQL
```

**Tasks:**
1. ✅ Verify MQTT publishing is working (use MQTT Explorer)
2. ✅ Check message format matches expected schema
3. ✅ Confirm QoS 1 delivery
4. ✅ Verify sample buffering works

### 7.2 Phase 2: Deploy Central Subscriber (Week 2)

```
[ADD CENTRAL SUBSCRIBER]

PLC Gateway                          MQTT Broker
    │                                     │
    │ ──── MQTT Publish ───────────────▶  │
    │                                     │
    └──── Direct DB Write (still) ────▶   │◀──── MQTT Subscribe ──┐
                                          │                        │
                                     Central Subscriber ──▶ PostgreSQL
```

**Tasks:**
1. 🆕 Create MqttSubscriberService.cs
2. 🆕 Subscribe to plc/+/tags
3. 🆕 Parse messages, apply rate control
4. 🆕 Write to unified historian_timeseries
5. ⚡ Compare: Direct write vs MQTT path (should match!)

### 7.3 Phase 3: Disable Direct Writes (Week 3)

```
[DISABLE DIRECT DB WRITES]

PLC Gateway                          MQTT Broker
    │                                     │
    │ ──── MQTT Publish ───────────────▶  │
    │                                     │
    │                                     │◀──── MQTT Subscribe ──┐
    X  PlcHistorianIngestService (DISABLED)                      │
                                     Central Subscriber ──▶ PostgreSQL
```

**Tasks:**
1. ⚠️ Disable PlcHistorianIngestService in appsettings.json
2. ✅ Verify data still flowing through MQTT
3. ✅ Monitor for gaps or duplicates
4. ✅ Run for 48 hours before removing code

### 7.4 Phase 4: Cleanup (Week 4)

**Tasks:**
1. ⚠️ Delete PlcHistorianIngestService.cs
2. ✅ Remove associated configuration
3. ✅ Update documentation
4. ✅ Close migration task

---

## 8. What Does NOT Change (PLC Gateway)

### 8.1 Complete List of Unchanged Components

| Component | Reason |
|-----------|--------|
| All PLC Drivers | Protocol communication - unaffected |
| PlcGatewayManager | Worker management - unaffected |
| PlcTagValuesPoolService | Shared cache - still needed for all consumers |
| PlcSampleBufferService | Multi-sample buffering - still needed for MQTT |
| PlcDataLoggingService | Parquet logging - separate concern |
| PlcConfigLoaderService | Config loading - unaffected |
| PlcConfigPersistenceService | Config saving - unaffected |
| MqttPublisher | Already exists - no changes |
| MultiProtocolPublisherService | Already exists - no changes |
| LocalTcpBroadcastService | Already exists - no changes |
| PlcController | REST API - unaffected |
| HealthPublisherService | Health metrics - unaffected |

### 8.2 Key Insight

**PLC Gateway is ALREADY 95% ready for decoupled architecture!**

The only change is:
- ⚠️ REMOVE: `PlcHistorianIngestService.cs` (embedded DB writes)
- 🆕 ADD: Central MQTT Subscriber (in separate service/process)

All transport mechanisms (MQTT, REST, TCP) already exist and work correctly.

---

## 9. Comparison: OPC vs PLC Architecture

### 9.1 Side-by-Side Comparison

| Aspect | OPC DA | PLC Gateway |
|--------|--------|-------------|
| **Protocol** | OLE/COM (DCOM for remote) | Various (S7, EIP, Modbus) |
| **Connection** | OPC DA 2.0 spec | Direct TCP/IP |
| **Platform** | Windows only (x86) | Cross-platform |
| **Drivers** | Single (OpcDaService) | Multiple (per manufacturer) |
| **MQTT Publisher** | 🆕 NEW (to be created) | ✅ EXISTS |
| **REST API** | ✅ EXISTS (OpcController) | ✅ EXISTS (PlcController) |
| **Local TCP** | ❌ Not needed | ✅ EXISTS |
| **Historian Ingest** | ⚠️ REMOVE | ⚠️ REMOVE |
| **Central Subscriber** | 🆕 NEW (shared) | 🆕 NEW (shared) |

### 9.2 Unified Data Flow (Future)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          UNIFIED ARCHITECTURE                               │
│                                                                             │
│   OPC DA Gateway (x86)              PLC Gateway (Any Platform)             │
│   ┌─────────────────┐               ┌─────────────────┐                    │
│   │ OpcDaService    │               │ PlcGatewayMgr   │                    │
│   │ TagValuesPool   │               │ TagValuesPool   │                    │
│   │ MqttPublisher 🆕│               │ MqttPublisher ✅│                    │
│   └────────┬────────┘               └────────┬────────┘                    │
│            │                                  │                             │
│            │ opc/+/tags                      │ plc/+/tags                  │
│            └─────────────┬───────────────────┘                             │
│                          ▼                                                  │
│                    MQTT Broker                                              │
│                          │                                                  │
│                          ▼                                                  │
│            ┌─────────────────────────┐                                     │
│            │ Central MQTT Subscriber │ 🆕 NEW (handles BOTH)               │
│            │ - Rate Control          │                                     │
│            │ - Batching              │                                     │
│            │ - Alarm Detection       │                                     │
│            └───────────┬─────────────┘                                     │
│                        ▼                                                    │
│            ┌─────────────────────────┐                                     │
│            │      PostgreSQL         │                                     │
│            │ historian_timeseries    │                                     │
│            │ (source_type: OPC/PLC)  │                                     │
│            └─────────────────────────┘                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Summary

### 10.1 PLC Gateway Changes Summary

| Category | Count | Details |
|----------|-------|---------|
| **✅ RETAINED** | 15+ modules | All drivers, pool, config, transport |
| **🔧 UPDATED** | 1 module | PlcDataLoggingService.cs (dual-mode local logging + batch_ref) |
| **⚠️ REMOVED** | 1 module | PlcHistorianIngestService.cs |
| **🆕 NEW** | 3 modules | BatchRecoveryApiService, Central MQTT Subscriber, BatchRecoveryService |

### 10.2 Key Takeaways

1. **PLC Gateway is already well-architected** for decoupled operation
2. **MQTT publishing already exists** and works correctly
3. **Unified batch_ref system**: `ddmmyyhhmmss` format for tracking every MQTT message
4. **Dual-mode local logging**: Choose Parquet files OR PostgreSQL buffer (configurable)
5. **Automatic recovery**: Central detects missing batches and requests from gateway
6. **Transport layer (MQTT/REST/TCP)** remains completely unchanged
7. **All drivers and worker management** remain completely unchanged

### 10.3 Key Architecture Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **batch_ref** | Every MQTT message | Unique ID (ddmmyyhhmmss) for tracking |
| **Local Storage** | Gateway (Parquet/PostgreSQL) | Durability during network outages |
| **batch_tracking** | Central DB | Tracks all received batches |
| **Recovery API** | Gateway `/api/recovery/batch/{ref}` | Returns missing data on request |
| **BatchRecoveryService** | Central Server | Detects gaps and triggers recovery |

### 10.4 Related Documents

- `ARCHITECTURE_OPC_CURRENT_VS_FUTURE.md` - OPC DA architecture comparison (same patterns)
- `DECOUPLED_MQTT_ARCHITECTURE.md` - Detailed design specification
- `copilot-instructions.md` - System overview and patterns

---

*Document Version: 2.0*  
*Updated: January 20, 2026*  
*Major Change: Added complete workflow diagram with unified batch reference system*  
*Added: Dual-mode local logging (Parquet/PostgreSQL), automatic batch recovery*  
*Scope: PLC Gateway Architecture*
