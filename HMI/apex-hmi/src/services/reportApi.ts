import api from "./api";

export interface DailyReportMeta {
  company: string;
  plant: string;
  report_title: string;
  date: string;
  generated_at: string;
  generated_by: string;
}

export interface DailyReportRow {
  s_no: number;
  group: string;
  parameter_unit: string;
  tag_id: string;
  display_label?: string;
  avg: number | null;
  max: number | null;
  min: number | null;
  hourly: Array<number | null>;
}

export interface DailyReportData {
  meta: DailyReportMeta;
  columns: string[];
  rows: DailyReportRow[];
  pagination?: {
    page: number;
    page_size: number;
    total_rows: number;
    total_pages: number;
  };
}

export async function fetchDailyReport(
  date: string,
  plant: string,
  area: string,
  sourceId: string | undefined,
  page: number,
  pageSize: number
): Promise<DailyReportData> {
  const response = await api.get("/reports/daily", { params: { date, plant, area, source_id: sourceId, page, page_size: pageSize } });
  return response.data;
}

export async function downloadDailyReportXlsx(date: string, plant: string, area: string, sourceId?: string): Promise<void> {
  const response = await api.get("/reports/daily/export", {
    params: { date, plant, area, source_id: sourceId, format: "xlsx" },
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Daily_Report_${area}_${plant}_${date}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/** Download only the filtered (currently visible) tags for a daily report. */
export async function downloadDailyReportXlsxFiltered(date: string, plant: string, area: string, tagIds: string[], sourceId?: string): Promise<void> {
  const response = await api.get("/reports/daily/export", {
    params: { date, plant, area, source_id: sourceId, tag_ids: tagIds.join(",") },
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Daily_Report_Filtered_${area}_${plant}_${date}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// ------------------------------------------------------------------ //
// Shift Report                                                         //
// ------------------------------------------------------------------ //

export interface ShiftDefinition {
  shift_code: string;
  shift_name: string;
  start_time: string;
  end_time: string;
}

export interface ShiftReportMeta {
  company: string;
  plant: string;
  report_title: string;
  date: string;
  shift_code: string;
  shift_name: string;
  shift_start: string;
  shift_end: string;
  generated_at: string;
  generated_by: string;
}

export interface ShiftReportRow {
  s_no: number;
  group: string;
  sub_equipment?: string;
  parameter_unit?: string;
  eng_unit?: string;
  tag_id: string;
  display_label?: string;
  description?: string;
  avg: number | null;
  max: number | null;
  min: number | null;
  hourly: Array<number | null>;
}

export interface ShiftReportData {
  meta: ShiftReportMeta;
  columns: string[];
  rows: ShiftReportRow[];
  pagination?: {
    page: number;
    page_size: number;
    total_rows: number;
    total_pages: number;
  };
}

export async function fetchActiveShifts(): Promise<ShiftDefinition[]> {
  const response = await api.get("/reports/shifts");
  return response.data?.shifts || [];
}

export async function fetchShiftReport(
  date: string,
  plant: string,
  area: string,
  sourceId: string | undefined,
  shiftCode: string,
  page: number,
  pageSize: number
): Promise<ShiftReportData> {
  const response = await api.get("/reports/shift", {
    params: { date, plant, area, source_id: sourceId, shift_code: shiftCode, page, page_size: pageSize },
  });
  return response.data;
}

export async function downloadShiftReportXlsx(
  date: string,
  plant: string,
  area: string,
  sourceId: string | undefined,
  shiftCode: string
): Promise<void> {
  const response = await api.get("/reports/shift/export", {
    params: { date, plant, area, source_id: sourceId, shift_code: shiftCode },
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Shift_Report_${area}_${plant}_${date}_${shiftCode}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/** Download only the filtered (currently visible) tags for a shift report. */
export async function downloadShiftReportXlsxFiltered(
  date: string,
  plant: string,
  area: string,
  sourceId: string | undefined,
  shiftCode: string,
  tagIds: string[]
): Promise<void> {
  const response = await api.get("/reports/shift/export", {
    params: { date, plant, area, source_id: sourceId, shift_code: shiftCode, tag_ids: tagIds.join(",") },
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Shift_Report_Filtered_${area}_${plant}_${date}_${shiftCode}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// ------------------------------------------------------------------ //
// Monthly Report                                                      //
// ------------------------------------------------------------------ //

export interface MonthlyReportMeta {
  company: string;
  plant: string;
  report_title: string;
  from_date: string;
  to_date: string;
  generated_at: string;
  generated_by: string;
}

export interface MonthlyReportRow {
  s_no: number;
  group: string;
  sub_equipment?: string;
  tag_id: string;
  description?: string;
  display_label?: string;
  eng_unit?: string;
  parameter_unit: string;
  avg: number | null;
  max: number | null;
  min: number | null;
  hourly: Array<number | null>;
}

export interface MonthlyReportData {
  meta: MonthlyReportMeta;
  columns: string[];
  rows: MonthlyReportRow[];
  pagination?: {
    page: number;
    page_size: number;
    total_rows: number;
    total_pages: number;
  };
}

export async function fetchMonthlyReport(
  fromDate: string,
  toDate: string,
  plant: string,   // comma-joined for multi-select
  area: string,    // comma-joined for multi-select
  sourceId: string | undefined,
  page: number,
  pageSize: number
): Promise<MonthlyReportData> {
  const response = await api.get("/reports/monthly", {
    params: {
      from_date: fromDate,
      to_date: toDate,
      plant,
      area,
      source_id: sourceId,
      page,
      page_size: pageSize,
    },
  });
  return response.data;
}

export async function downloadMonthlyReportXlsx(
  fromDate: string,
  toDate: string,
  plant: string,
  area: string,
  sourceId?: string
): Promise<void> {
  const response = await api.get("/reports/monthly/export", {
    params: { from_date: fromDate, to_date: toDate, plant, area, source_id: sourceId },
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Monthly_Report_${area}_${plant}_${fromDate}_to_${toDate}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/** Download only the filtered (currently visible) tags for a monthly report. */
export async function downloadMonthlyReportXlsxFiltered(
  fromDate: string,
  toDate: string,
  plant: string,
  area: string,
  tagIds: string[],
  sourceId?: string
): Promise<void> {
  const response = await api.get("/reports/monthly/export", {
    params: { from_date: fromDate, to_date: toDate, plant, area, source_id: sourceId, tag_ids: tagIds.join(",") },
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Monthly_Report_Filtered_${area}_${plant}_${fromDate}_to_${toDate}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
