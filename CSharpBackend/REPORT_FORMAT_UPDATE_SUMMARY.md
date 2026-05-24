# Report Format Update Summary

## CRITICAL INSTRUCTION
**Keep ALL current features:** Source filtering, tag multi-select, search, pagination, etc. **ONLY** change the Excel export format to match the reference files in the project root.

## Reference Files (Root Directory)
- `20250416_GTC2_Daily (1).xlsx` - Daily report format
- `20250421_GTC1_ShiftA.xlsx` - Shift report format
- `20250430_GTC1_Monthly.xlsx` - Monthly report format

## Excel Export Format Changes

### Daily Report (`export_to_excel` method in `report_service.py`)

**Current Format:**
```
Row 1-2: Company/Plant headers (columns I-M)
Row 3: Report title and date (merged cells)
Row 4: Headers (S.No | Equipment | Parameter/Unit | Tag Name | Avg | Max | Min | Hours...)
Rows 5+: Data
```

**Target Format (from 20250416_GTC2_Daily (1).xlsx):**
```
Row 1: "BHARAT ALUMINIUM COMPANY LIMITED ( PLANT- II )\nPOTLINE, FUME TREATMENT PLANT" (merged A1:AD1)
Row 2: [empty] [empty] "DAILY REPORT (CONTROL ROOM)" [empty] "DATE" "16-April-25" ...
Row 3: [empty] [empty] "Unit" "6 AM \n To 7 AM" "7 AM \n To 8 AM" ... "MIN" "MAX" "AVG"
Rows 4+: Tag_ID | Description | Unit | hourly_values... | min | max | avg
```

**Key Changes:**
1. **Column order**: Tag ID | Description | Unit | Hours | MIN | MAX | AVG  
   (NOT: S.No | Equipment | Parameter/Unit | Tag Name | Avg | Max | Min | Hours)
2. **Remove S.No column** - not in reference format
3. **Remove Equipment merging** - show tag ID and description separately
4. **Hour labels**: Format as "6 AM \n To 7 AM" with newline character
5. **Date format**: "dd-MMM-yy" (e.g., "16-April-25") NOT "YYYY-MM-DD"
6. **Statistics order**: MIN, MAX, AVG at the END (not Avg, Max, Min before hours)

### Shift Report

**Target Format (from 20250421_GTC1_ShiftA.xlsx):**
```
Row 1: Same company header
Row 2: [empty] [empty] [empty] "SHIFT REPORT (CONTROL ROOM)" ... "Shift A" "DATE" "21-April-25"
Row 3: [empty] [empty] "Unit" "5 AM \n To 6 AM" ... (8 hours) "Min" "Max" "Avg"
Rows 4+: Tag_ID | Description | Unit | shift_hours... | min | max | avg
```

**Key Differences from Daily:**
- Statistics: "Min", "Max", "Avg" (title case, not uppercase)
- Only 8 hourly columns (shift duration)
- Shift name in row 2

### Monthly Report

**Target Format (from 20250430_GTC1_Monthly.xlsx):**
```
Row 1: Same company header
Row 2: [empty] [empty] [empty] "Month" "4/1/2025" ... "MONTHLY REPORT"
Row 3: "S.No." "Equipment" [empty] "1st" "2nd" "3rd" ... "30th" "MIN" "MAX" "AVG"
Rows 4+: Tag_ID | Description | Unit | daily_values... | min | max | avg
```

**Key Differences:**
- **S.No. column** included (unlike daily/shift)
- Date columns: "1st", "2nd", "3rd", ..., "30th", "31st"
- Month format: "M/D/YYYY" (e.g., "4/1/2025")

## Web UI Format
**NO CHANGES** - Keep current table format with:
- S.No | Equipment | Parameter/Unit | Tag Name | Avg | Max | Min | Hours...
- All filtering features intact
- Tag multi-select dropdown
- Source/Plant/Area cascading filters
- Search box
- Pagination
- White professional theme with logo

## Implementation Notes

1. **Only modify `export_to_excel()` method** in `report_service.py`
2. **Do NOT change**:
   - Web UI table format (DailyReport.tsx, ShiftReport.tsx, MonthlyReport.tsx)
   - API response structure
   - Database queries
   - Filtering logic

3. **Test with**:
   - Multiple tags
   - Different plants/areas
   - Different date ranges
   - Ensure statistics (MIN/MAX/AVG) match reference files

## Column Width Standards (Excel)
- A (Tag ID): 25
- B (Description): 45
- C (Unit): 12
- D+ (Data columns): 12 each

## Border & Style Standards
- Black thin borders on all cells
- Blue header fill (#4472C4) with white bold text
- Numeric formatting: "0.00" (2 decimal places)
- Text alignment: Left for tag/description, Center for unit, Right for numbers
