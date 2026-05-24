import json, pandas as pd
from baseline_config_manager import BaselineConfigManager
from parquet_service import ParquetDataService
from config_reader import ConfigReader

start_date = '2025-02-09'
end_date = '2025-02-09'
production_tag = 'TURBINE_LOADMW'
coal_tag = 'TOTAL_COAL_FLOW'
steam_tag = 'MAIN_STEAM_FLOWTPH'

config = ConfigReader()
service = ParquetDataService(config.get_data_directory(), config.get_backup_directory())
base = BaselineConfigManager()

rated_capacity = base.get_rated_capacity(production_tag)
if rated_capacity is None:
    rated_capacity = 270.0  # fallback example

df = service.read_parquet_data(start_date, end_date, [production_tag, coal_tag, steam_tag])
if df.empty:
    print(json.dumps({'success': True, 'groups': [], 'message': 'No data'}))
    raise SystemExit

df['Timestamp'] = pd.to_datetime(df['Timestamp'])
df = df.sort_values('Timestamp')
for col in [production_tag, coal_tag, steam_tag]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

overall_mean_load = df[production_tag].dropna().mean()
ts_diffs = df['Timestamp'].diff().dropna().dt.total_seconds() / 60.0
sampling_minutes = ts_diffs.median() if len(ts_diffs) else 1.0
sampling_hours = sampling_minutes / 60.0
availability_threshold = rated_capacity * 0.05

results = []
for day, day_df in df.groupby(df['Timestamp'].dt.date):
    day_df_valid = day_df.dropna(subset=[production_tag])
    if day_df_valid.empty:
        continue
    avg_load = day_df_valid[production_tag].mean()
    sample_count = len(day_df_valid)
    hours_covered = sample_count * sampling_hours
    generation_mwh = avg_load * hours_covered
    above_thr = day_df_valid[day_df_valid[production_tag] > availability_threshold]
    availability_hours = len(above_thr) * sampling_hours
    availability_pct = (availability_hours / hours_covered * 100.0) if hours_covered else None
    performance_pct = (generation_mwh / (rated_capacity * hours_covered) * 100.0) if hours_covered else None
    quality_pct = 98.0
    oee_pct = (performance_pct * availability_pct * quality_pct) / 10000.0 if (performance_pct is not None and availability_pct is not None) else None
    coal_rate_tph = day_df[coal_tag].dropna().mean() if coal_tag in day_df.columns else None
    scc_kg_per_kwh = coal_rate_tph / avg_load if (coal_rate_tph is not None and avg_load) else None
    steam_flow_tph = day_df[steam_tag].dropna().mean() if steam_tag in day_df.columns else None
    results.append({
        'label': str(day),
        'avg_load_mw': round(avg_load,3),
        'generation_mwh': round(generation_mwh,3),
        'utilization_pct': round((avg_load / rated_capacity * 100.0),3),
        'availability_pct': round(availability_pct,3) if availability_pct is not None else None,
        'performance_pct': round(performance_pct,3) if performance_pct is not None else None,
        'quality_pct': quality_pct,
        'oee_pct': round(oee_pct,3) if oee_pct is not None else None,
        'coal_rate_tph': round(coal_rate_tph,3) if coal_rate_tph is not None else None,
        'steam_flow_tph': round(steam_flow_tph,3) if steam_flow_tph is not None else None,
        'scc_kg_per_kwh': round(scc_kg_per_kwh,5) if scc_kg_per_kwh is not None else None,
        'delta_from_mean_mw': round(avg_load - overall_mean_load,3),
        'delta_from_rated_mw': round(avg_load - rated_capacity,3)
    })

print(json.dumps({
    'success': True,
    'rated_capacity_mw': rated_capacity,
    'overall_mean_load_mw': round(overall_mean_load,3),
    'sampling_minutes': sampling_minutes,
    'availability_threshold_mw': round(availability_threshold,3),
    'groups': results
}, indent=2))
