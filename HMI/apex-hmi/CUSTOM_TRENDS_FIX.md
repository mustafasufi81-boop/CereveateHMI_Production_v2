# Custom Trends Fix - Date Range Issue Resolved

## Problem Identified
The custom trend date picker was using `type="date"` which only allows date selection **without time component**. This caused the following issues:

1. **Midnight Default**: When selecting dates, it defaulted to `00:00:00` (midnight) for both start and end
2. **Incomplete Data**: This resulted in missing data for most of the selected days
3. **Poor User Experience**: Users couldn't select specific time ranges within days

## Solution Applied

### Changes Made to `IndustrialHMIPrototype.tsx`

#### 1. Date Input Type Changed (Lines ~1571-1607)
**From:** `type="date"` → **To:** `type="datetime-local"`

This now allows users to select:
- ✅ Date (year, month, day)
- ✅ Time (hour, minute)
- ✅ Full timestamp precision

#### 2. Enhanced Date Validation (Lines ~801-828)
Added proper validation in `handleCustomDateApply`:
- ✅ Check that start date is before end date
- ✅ Validate maximum range (1 year / 365 days)
- ✅ Console logging for debugging
- ✅ User-friendly error messages

## How to Test

### 1. Build and Run
```bash
cd apex-hmi
npm run dev
```

### 2. Test Custom Date Range
1. Open the HMI dashboard
2. Switch any trend to **HISTORIAN** mode
3. Click the **CUSTOM** button
4. **Custom Range Picker** appears with:
   - FROM: `[datetime-local input]`
   - TO: `[datetime-local input]`
5. Select dates with specific times:
   - Example: FROM: `2026-02-01 08:00` TO: `2026-02-03 18:00`
6. Click **APPLY**
7. Trend should load historical data for the full selected range

### 3. Verify Data Display
- Check that data points appear across the entire date range
- Verify that all days within the range show data
- Confirm that time-of-day precision is preserved

## Expected Behavior

### Before Fix
- Input: `2026-02-01` to `2026-02-03`
- Actual Query: `2026-02-01 00:00:00` to `2026-02-03 00:00:00`
- Result: ❌ Only 2 days of data (Feb 1-2), Feb 3 data missing

### After Fix
- Input: `2026-02-01 00:00` to `2026-02-03 23:59`
- Actual Query: `2026-02-01 00:00:00` to `2026-02-03 23:59:00`
- Result: ✅ Full 3 days of data (Feb 1, 2, and 3 complete)

## Additional Features

### Date Range Validation
- **Maximum Range**: 1 year (365 days)
- **Invalid Range**: Shows alert if start ≥ end
- **User Feedback**: Clear error messages for invalid selections

### Console Logging
Check browser console for debugging:
```
[Custom Range] Applying: 2026-02-01T08:00:00.000Z to 2026-02-03T18:00:00.000Z (2220 minutes)
[Historian] Fetching tag Cooling_FAN_SPEED from 2026-02-01T08:00:00.000Z to 2026-02-03T18:00:00.000Z
[Historian] ✅ Updated trend data for Cooling_FAN_SPEED: 450 points
```

## Browser Compatibility

`datetime-local` input is supported in:
- ✅ Chrome/Edge 20+
- ✅ Firefox 57+
- ✅ Safari 14.1+
- ✅ Opera 11+

## Fallback for Older Browsers
If using older browsers, the input will fall back to text input where users can manually enter:
```
Format: YYYY-MM-DDTHH:MM
Example: 2026-02-01T08:00
```

## Related Files Modified
1. `apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx`
   - Lines ~1571-1607: Date picker UI
   - Lines ~801-828: Date validation logic

## Testing Checklist
- [ ] Custom date picker opens when CUSTOM button clicked
- [ ] Both date inputs show calendar + time picker
- [ ] Can select dates spanning multiple days
- [ ] APPLY button triggers data fetch
- [ ] Trend displays data for all selected days
- [ ] Validation prevents invalid ranges
- [ ] Cancel button closes picker without applying
- [ ] Console shows correct timestamp ranges

## Troubleshooting

### Issue: "No data showing"
- **Check 1**: Verify data exists in the database for selected range
- **Check 2**: Check browser console for API errors
- **Check 3**: Ensure selected tag has data in historian table

### Issue: "Input shows text instead of picker"
- **Reason**: Browser doesn't support `datetime-local`
- **Solution**: Manual entry or upgrade browser

### Issue: "Data cuts off mid-day"
- **Check**: Verify you selected time component (not just date)
- **Fix**: Set end time to `23:59` for full day coverage

## Performance Considerations

### Large Date Ranges
- The historian API automatically samples data if too many points
- Default limit: 500 points per tag
- For longer ranges (>7 days), consider using preset buttons (7D, 30D, etc.)

### Optimal Ranges
- **Hours/Days**: Use CUSTOM for precise time windows
- **Weeks**: Use preset buttons (7D, 30D)
- **Months**: Use 30D or 90D presets
- **Maximum**: 1 year with automatic sampling

## Future Enhancements

Potential improvements for future versions:
1. Add time zone selector
2. Quick time presets (morning, afternoon, evening)
3. Date range templates (work week, weekend, etc.)
4. Remember last custom range
5. Export custom range as bookmark

---

**Status**: ✅ **FIXED** - Custom trends now support full datetime selection for all days
**Date**: February 4, 2026
**Impact**: High - Resolves major usability issue with custom date ranges
