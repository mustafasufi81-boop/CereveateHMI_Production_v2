# Alarm Panel Enhancements - ISA-18.2 Compliant

## New Features Implemented

### 1. ✅ Alarm Help Tooltips (ISA-18.2 Operator Guidance)

**Purpose**: Provide context-sensitive operator guidance on what actions to take for each alarm type.

**Implementation**:
- **Help Button**: Blue `?` icon button next to audit trail button in alarm footer
- **Click to Show/Hide**: Toggle help panel below alarm card
- **Intelligent Guidance**: Customized instructions based on:
  - Tag type (TT, PT, FT, LT, VT, CT, ST per ISA-5.1)
  - Alarm direction (High vs. Low)
  - Priority level (Critical vs. normal)

**Tag-Specific Guidance Included**:

| Tag Type | Description | Guidance Provided |
|----------|-------------|-------------------|
| **TT** | Temperature Transmitter | High: Check cooling system, verify flow<br>Low: Check heating, verify steam supply |
| **PT** | Pressure Transmitter | High: Check PRVs, verify relief paths<br>Low: Check for leaks, verify pumps |
| **FT** | Flow Transmitter | High: Check valve position, verify differential<br>Low: Check blockage, verify pump operation |
| **LT** | Level Transmitter | High: Check outlet flow, verify control valve<br>Low: Check inlet flow, verify for leaks |
| **VT** | Vibration Transmitter | Check bearings, lubrication, balance, alignment<br>Shutdown guidance if >10 mm/s |
| **CT/ST** | Current/Speed Transmitter | High: Check motor load, mechanical binding<br>Low: Verify motor running, check VFD |

**Example Help Panel Content**:
```
🔵 High Vibration Alarm
Operator Guidance (ISA-18.2)

Recommended Actions:
1. IMMEDIATELY reduce load if vibration is severe
2. Check for bearing wear or lubrication issues
3. Inspect for unbalance, misalignment, or looseness
4. Verify coupling and mounting bolt tightness
5. Check for resonance or process-induced vibration
6. If >10 mm/s: Consider emergency shutdown

⚠️ CRITICAL: High vibration can cause catastrophic bearing 
or shaft failure. Shutdown if vibration increases rapidly.

Note: Always follow site-specific operating procedures 
and safety protocols.
```

**ISA-18.2 Compliance**:
- ✅ Context-sensitive help for each alarm type
- ✅ Priority-based safety warnings
- ✅ Step-by-step action guidance
- ✅ Reminds operators to follow site procedures
- ✅ Reduces response time and errors

---

### 2. ✅ Tag-Based Alarm Search

**Purpose**: Allow operators to quickly filter alarms by tag name for focused troubleshooting.

**Implementation**:
- **Search Bar**: Located at top of alarm list (below header)
- **Real-time Filtering**: Instant filter as you type
- **Case-Insensitive**: Matches `TT-101`, `tt-101`, `TT-101`, etc.
- **Matches Both**: Tag name and tag ID
- **Clear Button**: `X` button to clear search quickly
- **Result Count**: Shows "Showing N alarm(s) matching 'search'"

**Usage Examples**:

```
Search: "TT"       → Shows all temperature alarms (TT-101, TT-102, etc.)
Search: "101"      → Shows all alarms for equipment 101 (TT-101, PT-101, ST-101)
Search: "VT-101"   → Shows only vibration alarm VT-101
Search: "motor"    → Shows all motor-related tags (if in tag name)
```

**Benefits**:
- ✅ Quick isolation of specific equipment alarms
- ✅ Easy troubleshooting during multiple simultaneous alarms
- ✅ Filter by equipment number (e.g., "101" shows all C-101 alarms)
- ✅ Filter by measurement type (TT, PT, FT, etc.)
- ✅ Non-destructive - just hides non-matching alarms
- ✅ Works with "Show Cleared" toggle

---

## Usage Instructions

### For Operators:

**Using Help Tooltips:**
1. Find alarm you need guidance on
2. Click the blue `?` (Help) button in alarm footer
3. Read the step-by-step actions
4. Follow recommendations in order
5. Click `?` again to hide help
6. Document actions in alarm clear notes

**Using Tag Search:**
1. Click in search box at top of alarm list
2. Type tag name or part of tag name
3. See filtered results instantly
4. Click `X` or clear text to see all alarms again
5. Search works with "Show Cleared" toggle

**Best Practices:**
- Use help for unfamiliar alarm types
- Search by equipment number during upsets
- Keep help open while performing actions
- Always acknowledge alarms after reading help

---

## Technical Details

### Help System Architecture

**Function**: `getAlarmHelp(alarm: Alarm)`
- Input: Alarm object
- Output: { title, steps[], safety }
- Logic: 
  1. Extract tag prefix (first 2 chars)
  2. Detect high/low from message
  3. Map to ISA-5.1 tag standard
  4. Return customized guidance

**State Management**:
```typescript
const [showHelp, setShowHelp] = useState<number | null>(null);
// Stores alarm ID of currently shown help (null = none)
```

**Rendering**:
- Conditionally rendered below alarm card
- Blue theme to distinguish from alarm card
- Collapsible by clicking help button again
- Only one help panel shown at a time

### Search Architecture

**State Management**:
```typescript
const [searchTag, setSearchTag] = useState("");
// Stores current search query
```

**Filtering Logic**:
```typescript
if (searchTag.trim()) {
  displayedAlarms = displayedAlarms.filter(a => 
    a.tag_name.toLowerCase().includes(searchTag.toLowerCase()) ||
    a.tag_id.toLowerCase().includes(searchTag.toLowerCase())
  );
}
```

**UI Components**:
- Input field with Search icon
- Clear button (X) when text present
- Result count display
- Placeholder text: "Search by tag name..."

---

## ISA-18.2 Compliance

### Requirements Met:

**Operator Support (Section 6.2.3)**:
- ✅ Context-sensitive help for alarm types
- ✅ Clear action steps provided
- ✅ Safety warnings for critical conditions
- ✅ Reference to follow site procedures

**Alarm Presentation (Section 6.2.1)**:
- ✅ Quick filtering by tag for focus
- ✅ Non-destructive search (doesn't hide alarms permanently)
- ✅ Maintains priority sorting during search
- ✅ Result count for situational awareness

**Response Facilitation (Section 6.2.4)**:
- ✅ Reduces time to understand alarm
- ✅ Guides correct corrective actions
- ✅ Prevents incorrect operator responses
- ✅ Improves alarm response effectiveness

---

## Future Enhancements (Roadmap)

### Phase 2:
- [ ] Alarm help in multiple languages
- [ ] Link to detailed P&ID drawings
- [ ] Video tutorials for complex procedures
- [ ] Integration with work order system

### Phase 3:
- [ ] Advanced search (by priority, date, state)
- [ ] Saved search filters
- [ ] Export filtered alarms to PDF
- [ ] Alarm analytics per tag type

---

## Testing Checklist

**Help Tooltips:**
- [x] Help button visible in alarm footer
- [x] Click shows blue help panel
- [x] Click again hides help panel
- [x] Only one help shown at a time
- [x] Correct guidance for TT, PT, FT, LT, VT, CT, ST tags
- [x] High vs. Low detection works
- [x] Critical alarms show safety warnings
- [x] Help panel responsive on small screens

**Tag Search:**
- [x] Search box visible at top of alarm list
- [x] Type to filter in real-time
- [x] Case-insensitive matching works
- [x] Clear button appears when text present
- [x] Clear button empties search
- [x] Result count displays correctly
- [x] Search works with cleared alarms filter
- [x] Maintains priority sorting

---

## Support

**Questions?** Contact HMI Development Team

**ISA-18.2 Reference**: "Management of Alarm Systems for the Process Industries"  
**ISA-5.1 Reference**: "Instrumentation Symbols and Identification"

---

**Version**: 1.0  
**Date**: February 1, 2026  
**Status**: Production Ready ✅
