/**
 * HmiReportsTab — embedded Reports panel inside the main HMI tab bar.
 * Sub-tabs: Shift Report | Daily Report | Monthly Report
 * Opens each report page in a full-height scrollable iframe-like container.
 * canGenerate controls whether the export/download buttons are shown (passed
 * down via the permission prop; each report page already gates its own download
 * button via usePermission — this is just an extra guard at the tab level).
 */
import { useState } from "react";
import type { CSSProperties } from "react";
import ShiftReport  from "@/pages/reports/ShiftReport";
import DailyReport  from "@/pages/reports/DailyReport";
import MonthlyReport from "@/pages/reports/MonthlyReport";

type ReportSubTab = 'shift' | 'daily' | 'monthly';

interface Props {
  canGenerate: boolean;
}

export function HmiReportsTab({ canGenerate }: Props) {
  const [sub, setSub] = useState<ReportSubTab>('shift');

  const tabStyle = (active: boolean): CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: '5px',
    padding: '0 16px',
    fontSize: '11px', fontWeight: 700, letterSpacing: '0.8px',
    cursor: 'pointer', background: 'none', border: 'none',
    borderBottom: active ? '2px solid #10B981' : '2px solid transparent',
    borderTop: '2px solid transparent',
    color: active ? '#34D399' : '#6B7280',
    fontFamily: 'Consolas, monospace', textTransform: 'uppercase',
    transition: 'color 0.15s, border-color 0.15s',
    whiteSpace: 'nowrap',
    height: '36px',
  });

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', backgroundColor: '#0d1117' }}>

      {/* Sub-tab bar */}
      <div style={{
        display: 'flex', alignItems: 'stretch', gap: '2px',
        borderBottom: '1px solid #1F2937',
        backgroundColor: '#080D14',
        flexShrink: 0, paddingLeft: '8px',
      }}>
        <button style={tabStyle(sub === 'shift')}   onClick={() => setSub('shift')}>
          🕐 Shift Report
        </button>
        <div style={{ width: '1px', backgroundColor: '#1F2937', margin: '8px 2px' }} />
        <button style={tabStyle(sub === 'daily')}   onClick={() => setSub('daily')}>
          📅 Daily Report
        </button>
        <div style={{ width: '1px', backgroundColor: '#1F2937', margin: '8px 2px' }} />
        <button style={tabStyle(sub === 'monthly')} onClick={() => setSub('monthly')}>
          📆 Monthly Report
        </button>
      </div>

      {/* Report content — full height, scrollable */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
        {sub === 'shift'   && <ShiftReport />}
        {sub === 'daily'   && <DailyReport />}
        {sub === 'monthly' && <MonthlyReport />}
      </div>
    </div>
  );
}
