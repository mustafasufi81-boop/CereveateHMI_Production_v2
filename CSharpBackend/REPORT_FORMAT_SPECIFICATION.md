# Report Format Specification

## Common Header Structure (All Reports)

### Row 0: Company Name & Plant
```
BHARAT ALUMINIUM COMPANY LIMITED ( PLANT- II )
POTLINE, FUME TREATMENT PLANT
```

### Row 1: Report Title & Date Section
**Daily Report:**
```
Column 0-1: Empty
Column 2: "DAILY REPORT (CONTROL ROOM)"
Column 3: Empty
Column 4: "DATE"
Column 5: "16-April-25"  (dd-MMM-yy format)
```

**Shift Report:**
```
Column 0-2: Empty
Column 3: "SHIFT REPORT (CONTROL ROOM)"
Column 10: "Shift A" / "Shift B" / "Shift C"
Column 11: "DATE"
Column 12: "21-April-25"  (dd-MMM-yy format)
```

**Monthly Report:**
```
Column 0-2: Empty
Column 3: "Month"
Column 4: "4/1/2025"  (M/D/YYYY format)
Column 10: "MONTHLY REPORT"
```

## Column Headers (Row 2)

### Daily Report Structure
```
Column 0: Empty
Column 1: Empty
Column 2: "Unit"
Column 3+: Hourly time slots (24 columns)
  - "6 AM \n To 7 AM"
  - "7 AM \n To 8 AM"
  - ... (24 hours)
  - "5 AM \n To 6 AM"
Last 3: "MIN", "MAX", "AVG"
```

### Shift Report Structure
```
Column 0: Empty
Column 1: Empty  
Column 2: "Unit"
Column 3+: Hourly time slots (8 columns for shift duration)
  - "5 AM \n To 6 AM"
  - "6 AM \n To 7 AM"
  - ... (8 hours)
Last 3: "Min", "Max", "Avg"
```

### Monthly Report Structure
```
Column 0: "S.No."
Column 1: "Equipment"
Column 2: Empty
Column 3+: Daily columns (30/31 columns)
  - "1st", "2nd", "3rd", "4th", ... "30th", "31st"
Last 3: "MIN", "MAX", "AVG"
```

## Data Row Structure

### Columns 0-2 (Equipment Information)
- **Column 0**: Tag ID (e.g., `MDRM_400_TT01.Val.PV`)
- **Column 1**: Description (e.g., `GTC inlet gas temperature section 7`)
- **Column 2**: Unit (e.g., `°C`, `kPa`, `T/h`, `Nm3/s`)

### Columns 3 to End-3 (Time-series Data)
- Daily: 24 hourly average values
- Shift: 8 hourly average values
- Monthly: 30/31 daily average values

### Last 3 Columns (Statistics)
- MIN: Minimum value across time period
- MAX: Maximum value across time period
- AVG: Average value across time period

## Key Formatting Rules

1. **Header Case Sensitivity**:
   - Daily: "MIN", "MAX", "AVG" (uppercase)
   - Shift: "Min", "Max", "Avg" (title case)
   - Monthly: "MIN", "MAX", "AVG" (uppercase)

2. **Date Formats**:
   - Daily: "16-April-25" (dd-MMM-yy)
   - Shift: "21-April-25" (dd-MMM-yy)
   - Monthly: "4/1/2025" (M/D/YYYY)

3. **Time Labels**:
   - Use `\n` for line breaks in hour ranges
   - Format: "6 AM \n To 7 AM"

4. **Missing Values**:
   - Use empty cells (not "-" or "NaN")
   - Statistics calculated only from valid data points

5. **S.No. Column** (Monthly Only):
   - Row 3 starts from 1
   - Sequential numbering for each data row

## Equipment Description Standards

Based on existing tag descriptions in database tag_master:
- Use human-readable descriptions
- Include location/section numbers
- Format: `<Equipment Type> <Location/Section>`
  - Example: "GTC inlet gas temperature section 7"
  - Example: "Fresh alumina flow rate"
  - Example: "GTC gas flow at stack"

## Statistical Calculation Notes

- **MIN**: `min(all_values)` across the time period
- **MAX**: `max(all_values)` across the time period  
- **AVG**: `avg(all_values)` - overall average of time period
- Exclude NULL/missing values from calculations
- Round to appropriate decimal places based on data type
