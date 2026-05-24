# Excel Report Column Order Fix - December 2025

## Problem Identified
User reported that daily report Excel exports had incorrect column headers and order:
- **Wrong**: `Tag ID | Description | Unit | 12am-1am | ... | MIN | MAX | AVG`
- **Required**: `Equipment | Sub Unit | Tag Name | Tag Description | Unit | 6am-7am | ... | MIN | MAX | AVG`

## Changes Applied

### 1. Daily Report Export (`report_service.py` - `export_to_excel()` method)

#### Column Headers (Row 3)
**Before:**
```python
headers_row = ["", "", "Unit"] + hour_labels + ["MIN", "MAX", "AVG"]
```

**After:**
```python
headers_row = ["Equipment", "Sub Unit", "Tag Name", "Tag Description", "Unit"] + hour_labels + ["MIN", "MAX", "AVG"]
```

#### Data Row Structure
**Before:**
```python
[row["s_no"], row["group"], row["parameter_unit"], row["display_label"], row["avg"], row["max"], row["min"], *row["hourly"]]
```

**After:**
```python
[
    row.get("group") or "",                    # Equipment
    "",                                         # Sub Unit (empty for now)
    row["tag_id"],                              # Tag Name
    row.get("display_label") or row["tag_id"], # Tag Description
    row.get("parameter_unit") or "",            # Unit
    *row["hourly"],                             # Hourly values (6am-5am)
    row["min"],                                 # MIN
    row["max"],                                 # MAX
    row["avg"],                                 # AVG
]
```

#### Hour Start Time
**Before:** Hours started from 12am (midnight)
**After:** Hours start from 6am (industrial shift standard)

Modified methods:
- `_hour_columns()`: Now starts from "6 am To 7 am"
- `_ordered_hours()`: Returns `[6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,0,1,2,3,4,5]`

#### Column Widths
Updated to accommodate new column structure:
```python
"A": 22,  # Equipment
"B": 18,  # Sub Unit
"C": 24,  # Tag Name
"D": 40,  # Tag Description
"E": 12,  # Unit
"F"-"AC": 14  # Hourly columns and stats (MIN/MAX/AVG)
```

#### Cell Merging Logic
- **Equipment column (A)**: Merge cells with same equipment name
- **Unit column (E)**: Merge cells with same unit
- Removed old S.No and group column merge logic (columns B, C)

### 2. Shift Report Export (`export_shift_to_excel()` method)

Applied identical column structure changes:
- Headers: `["Equipment", "Sub Unit", "Tag Name", "Tag Description", "Unit"] + hour_labels + ["Min", "Max", "Avg"]`
- Data rows follow same format as daily report
- Column widths updated to match daily report
- Cell alignment and number formatting adjusted for new column positions

### 3. Monthly Report Export
Monthly report already had correct structure with S.No column - no changes needed.

## Technical Details

### Statistics Column Position
**CRITICAL FIX**: MIN/MAX/AVG now appear **AFTER** hourly values, not before:
- Old: `[metadata, stats, hourly_values]`
- New: `[metadata, hourly_values, stats]`

### Sub Unit Column
Currently set to empty string (`""`) as database schema doesn't have explicit sub_unit field. Can be populated later if hierarchical tag structure is implemented.

### Database Field Mapping
| Excel Column | Database Field | Notes |
|--------------|----------------|-------|
| Equipment | `group` or `group_name` | From tag master |
| Sub Unit | (empty) | Future implementation |
| Tag Name | `tag_id` | Primary identifier |
| Tag Description | `display_label` or `tag_id` | Fallback to tag_id if no label |
| Unit | `parameter_unit` | Measurement unit |

### Cell Formatting
- **Header row (row 3)**: Blue fill (#4472C4), white bold text, centered, wrapped
- **Equipment/Tag columns**: Left-aligned, wrapped text
- **Unit column**: Center-aligned
- **Numeric values**: Right-aligned, "0.00" number format
- **Stats columns (MIN/MAX/AVG)**: Yellow summary fill

## Testing Checklist

- [x] Daily report Excel export generates with correct columns
- [x] Shift report Excel export generates with correct columns
- [x] Hour labels start from 6am instead of 12am
- [x] Statistics (MIN/MAX/AVG) appear at the end
- [x] Column widths appropriate for data
- [x] Cell merging works for Equipment and Unit columns
- [x] Flask backend restarted (PID 35464)
- [ ] User validation with actual exported file

## Files Modified
1. `WEB_HMI_MFA/HMI/services/report_service.py`
   - Lines 280-395: Daily report export
   - Lines 1021-1078: Shift report export
   - Lines 22-51: Hour order methods

## Deployment Status
- **Flask Backend**: Restarted successfully (port 6001, PID 35464)
- **Changes Applied**: December 2025
- **Immediate Effect**: All new Excel exports will use corrected format

## Future Enhancements
1. Implement `sub_unit` field in database schema for hierarchical tag organization
2. Consider user preference for hour start time (6am vs 12am)
3. Add column visibility toggles in web UI settings

---
**Created**: December 2025  
**Status**: ✅ COMPLETED  
**Validated**: Pending user confirmation
