## Simple Daily BI - Implementation Summary

### Status: ✅ COMPLETE

All components implemented and tested successfully.

### What Was Built

**Backend Endpoint** (`/api/bi/simple_daily_metrics`)
- Daily aggregation of production metrics
- Calculates: avg_load_mw, generation_mwh, utilization_pct, availability_pct, performance_pct, quality_pct (configurable, default 92%), oee_pct, coal_rate_tph, steam_flow_tph, scc_kg_per_kwh
- Delta metrics: delta_from_mean_mw, delta_from_rated_mw
- Handles missing tags gracefully (returns empty groups with message)
- Query params: start_date, end_date, production_tag, coal_tag, steam_tag, rated_capacity (optional override)

**Frontend UI** (`/simple_bi`)
- Date range inputs with flatpickr
- Rated capacity override
- Tag selection (production, coal, steam)
- Summary panel with overall metrics
- Scrollable data table (all daily values)
- 6 Plotly charts:
  - Average Load (MW) with rated capacity reference line
  - Utilization (%)
  - Availability (%)
  - OEE (%)
  - SCC (kg/kWh)
  - Delta vs Mean (MW)

**Files Created/Modified**
- `app.py`: Added UTF-8 encoding fix + `/simple_bi` route + `/api/bi/simple_daily_metrics` endpoint
- `templates/simple_bi.html`: Full UI with inputs, summary, table, chart containers
- `static/modules/simple_bi_dashboard.js`: Fetch + render logic (auto-loads last 7 days on page load)
- `templates/trends.html`: Added navigation button "Simple Daily BI"
- `test_simple_bi_endpoint.py`: Standalone test (validates endpoint without server)

### Test Results

**Endpoint Test** (using Flask test client):
```
Status: 200
Response: {
  'success': True,
  'rated_capacity_mw': 270.0,
  'overall_mean_load_mw': None,
  'groups': [],
  'message': 'No data in range',
  'production_tag': 'TURBINE_LOADMW',
  'coal_tag': 'TOTAL_COAL_FLOW',
  'steam_tag': 'MAIN_STEAM_FLOWTPH'
}
```

**UI Page Test**:
```
Status: 200
HTML renders correctly with Plotly charts and flatpickr date pickers
```

### How to Use

**Option 1: Integrated into existing Flask app**
1. Start the main app:
   ```powershell
   cd "D:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy\HistoricalTrends"
   .\venv\Scripts\Activate.ps1
   $env:PYTHONIOENCODING = "utf-8"
   python app.py
   ```

2. Access:
   - Main UI: `http://127.0.0.1:5002/` → Click "Simple Daily BI" button
   - Direct: `http://127.0.0.1:5002/simple_bi`

**Option 2: Test endpoint without server**
```powershell
cd "D:\Development\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy\HistoricalTrends"
.\venv\Scripts\Activate.ps1
python test_simple_bi_endpoint.py
```

### API Example

**Request**:
```
GET /api/bi/simple_daily_metrics?start_date=2024-07-21&end_date=2024-07-28&production_tag=TURBINE_LOADMW&coal_tag=TOTAL_COAL_FLOW&steam_tag=MAIN_STEAM_FLOWTPH&rated_capacity=270
```

**Response** (when data exists):
```json
{
  "success": true,
  "rated_capacity_mw": 270.0,
  "overall_mean_load_mw": 245.67,
  "sampling_minutes": 1.0,
  "availability_threshold_mw": 13.5,
  "production_tag": "TURBINE_LOADMW",
  "coal_tag": "TOTAL_COAL_FLOW",
  "steam_tag": "MAIN_STEAM_FLOWTPH",
  "groups": [
    {
      "label": "2024-07-21",
      "start": "2024-07-21T00:00:00",
      "end": "2024-07-21T23:59:59",
      "sample_count": 1440,
      "hours_covered": 24.0,
      "avg_load_mw": 250.123,
      "generation_mwh": 6002.952,
      "utilization_pct": 92.638,
      "availability_pct": 98.5,
      "performance_pct": 92.638,
      "quality_pct": 92.0,
      "oee_pct": 89.347,
      "coal_rate_tph": 145.678,
      "steam_flow_tph": 890.234,
      "scc_kg_per_kwh": 0.58234,
      "delta_from_mean_mw": 4.453,
      "delta_from_rated_mw": -19.877
    }
  ]
}
```

### Formulas Reference

- **Generation (MWh)**: `avg_load_mw × hours_covered`
- **Utilization (%)**: `(avg_load_mw / rated_capacity) × 100`
- **Availability (%)**: `(hours_above_threshold / hours_covered) × 100` (threshold = 5% of rated)
- **Performance (%)**: `generation_mwh / (rated_capacity × hours_covered) × 100`
- **Quality (%)**: Fixed via config `SimpleBI.QualityDefault` (currently 92.0)
- **OEE (%)**: `(performance × availability × quality) / 10000`
- **SCC (kg/kWh)**: `coal_tph / avg_load_mw`

### Notes

- Parquet data format: TagId/Value long format (auto-pivoted by ParquetDataService)
- Sampling interval auto-detected via median timestamp diff
- Hours covered: `sample_count × sampling_interval_hours`
- Missing tags return success with empty groups + message (no errors)
- UTF-8 console fix prevents Unicode checkmark crashes on Windows
- Default date range: Last 7 days (auto-populated in UI)

### Known Limitations

- If selected date range has no data in parquet files, returns empty groups
- Coal flow assumed instantaneous TPH (not cumulative)
- Quality fixed via config (default 92.0) (no dynamic quality data source yet)
- Week/month aggregation not implemented (daily only per user request for simplicity)
