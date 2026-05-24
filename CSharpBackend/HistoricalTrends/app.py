from flask import Flask, render_template, request, jsonify, send_file
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import io
import math
import os
import pandas as pd
import numpy as np
import threading
import sys

# Fix Unicode output encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from config_reader import ConfigReader
from db_data_service import DBDataService
from interpolation_cache_service import InterpolationCacheService
from predictive_interpolation_service import PredictiveInterpolationService
from derived_analytics_manager import DerivedAnalyticsManager
from baseline_config_manager import BaselineConfigManager
from downtime_tracking_service import DowntimeTrackingService


class _SafeJSONProvider(DefaultJSONProvider):
    """Flask JSON provider that converts NaN / Inf / -Inf to null and handles
    numpy / pandas types so jsonify() never raises TypeError or ValueError."""

    @staticmethod
    def _default(obj):
        """Called by json.dumps for objects not natively serializable."""
        import numpy as np
        import pandas as pd
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if hasattr(obj, 'item'):          # generic numpy scalar fallback
            return obj.item()
        return str(obj)

    def dumps(self, obj, **kwargs):
        kwargs.setdefault('default', self._default)
        kwargs.setdefault('ensure_ascii', False)
        return json.dumps(obj, **kwargs)

    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)



app = Flask(__name__)
app.json_provider_class = _SafeJSONProvider
app.json = _SafeJSONProvider(app)


def _safe_records(df: pd.DataFrame) -> list:
    """Convert DataFrame to list-of-dicts with NaN/Inf → None (pandas-2.0 safe)."""
    raw_json = df.to_json(orient='records', date_format='iso', default_handler=str)
    return json.loads(raw_json)

app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app)

# Initialize services
config = ConfigReader()

# Load trends-specific configuration
trends_config_path = os.path.join(os.path.dirname(__file__), 'trends-config.json')
with open(trends_config_path, 'r', encoding='utf-8') as f:
    trends_config = json.load(f)

simple_bi_config = trends_config.get('SimpleBI', {})
SIMPLE_BI_QUALITY_DEFAULT = float(simple_bi_config.get('QualityDefault', 92.0))

# Use paths from trends-config.json
paths = trends_config.get('Paths', {})
data_service = DBDataService()

# Load performance settings from trends-config.json
perf_config = trends_config.get('Performance', {})
MAX_BOXPLOT_SAMPLES = perf_config.get('MaxBoxPlotSamples', 5000)
MAX_DISTRIBUTION_SAMPLES = perf_config.get('MaxDistributionSamples', 10000)
MAX_CHART_DATA_POINTS = perf_config.get('MaxChartDataPoints', 50000)

# Initialize baseline config manager
baseline_config = BaselineConfigManager()

# Initialize downtime tracking service
downtime_service = DowntimeTrackingService()

# Initialize interpolation cache service
interpolation_service = InterpolationCacheService(config.get_data_directory())

# Initialize predictive interpolation service
predictive_service = PredictiveInterpolationService(config.get_data_directory())

# Initialize derived analytics manager
derived_manager = DerivedAnalyticsManager()

# Store for async prediction tasks
prediction_tasks = {}

@app.route('/')
def index():
    """Main historical trends page"""
    import time
    return render_template('trends.html', v=int(time.time()))

@app.route('/test')
def test_api():
    """JavaScript API test page"""
    return render_template('test_js_api_calls.html')

@app.route('/test_pivot_api')
def test_pivot_api():
    """Pivot Table API test page"""
    return render_template('test_pivot_api.html')

@app.route('/api/v1/analytics/pivot_statistics', methods=['POST'])
def calculate_pivot_statistics():
    """Calculate statistics for pivot table - returns properly formatted numeric values"""
    try:
        import numpy as np
        import pandas as pd
        
        data = request.json
        dataset = pd.DataFrame(data['data'])
        tags = data['tags']
        
        print(f"[Pivot API] Received {len(dataset)} rows for {len(tags)} tags")
        print(f"[Pivot API] Dataset columns: {list(dataset.columns)}")
        print(f"[Pivot API] Sample row: {dataset.iloc[0].to_dict() if len(dataset) > 0 else 'No data'}")
        
        stats_result = {}
        
        for tag in tags:
            if tag not in dataset.columns:
                print(f"[Pivot API] Tag '{tag}' not in dataset")
                stats_result[tag] = {'count': 0, 'mean': None, 'min': None, 'max': None, 'std_dev': None, 'sum': None}
                continue
                
            # Get numeric values only
            values = pd.to_numeric(dataset[tag], errors='coerce').dropna()
            
            print(f"[Pivot API] Tag '{tag}': {len(values)} valid values out of {len(dataset)}")
            
            if len(values) == 0:
                stats_result[tag] = {'count': 0, 'mean': None, 'min': None, 'max': None, 'std_dev': None, 'sum': None}
                continue
            
            stats_result[tag] = {
                'count': int(len(values)),
                'mean': float(values.mean()),
                'min': float(values.min()),
                'max': float(values.max()),
                'std_dev': float(values.std()),
                'sum': float(values.sum())
            }
            
            print(f"[Pivot API] Tag '{tag}' stats: {stats_result[tag]}")
        
        return jsonify({'success': True, 'stats': stats_result})
    except Exception as e:
        print(f"[Pivot API] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files')
def get_files():
    """Get list of available parquet files"""
    try:
        files = data_service.get_available_files()
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tags')
def get_tags():
    """Get list of available tags enriched with metadata from tag_master"""
    try:
        from db_pool import borrow_connection
        import math
        with borrow_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        m.tag_id,
                        COALESCE(m.tag_name, m.tag_id)              AS tag_name,
                        COALESCE(m.server_progid, 'Unknown Source') AS server_progid,
                        COALESCE(m.description, '')                 AS description,
                        COALESCE(m.eng_unit, '')                    AS eng_unit
                    FROM historian_meta.tag_master m
                    WHERE m.enabled = true
                      AND EXISTS (
                          SELECT 1 FROM historian_raw.historian_timeseries t
                          WHERE t.tag_id = m.tag_id
                            AND t.value_num IS NOT NULL
                          LIMIT 1
                      )
                    ORDER BY COALESCE(m.server_progid, 'Unknown Source'), m.tag_id
                """)
                rows = cur.fetchall()
        tags = [
            {
                'tag_id':      r[0],
                'tag_name':    r[1],
                'server_progid': r[2],
                'description': r[3],
                'eng_unit':    r[4]
            }
            for r in rows
        ]
        return jsonify({'success': True, 'tags': tags})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data')
def get_data():
    """Get trend data for specified date range and tags"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        tags_param = request.args.get('tags')
        force_raw = request.args.get('force_raw', '0') in ('1', 'true', 'True')
        
        # Parse tags - handle both JSON array and comma-separated string
        tags = None
        if tags_param:
            try:
                tags = json.loads(tags_param)  # Try JSON first (from frontend)
            except json.JSONDecodeError:
                tags = [t.strip() for t in tags_param.split(',')]  # Fallback to CSV (from tests)
        
        # Guard: Force RAW is limited to 20 days and 5 tags to prevent runaway queries
        if force_raw:
            import dateutil.parser as _dp
            _s = _dp.parse(start_date).replace(tzinfo=None) if start_date else None
            _e = _dp.parse(end_date).replace(tzinfo=None) if end_date else None
            if _s and _e and (_e - _s).days > 20:
                return jsonify({
                    'success': False,
                    'error': f'Force RAW mode is limited to 20 days. Your range is {(_e - _s).days} days. Shorten the range or disable Force RAW.'
                }), 400
            if tags and len(tags) > 5:
                return jsonify({
                    'success': False,
                    'error': f'Force RAW mode is limited to 5 tags. You selected {len(tags)} tags. Deselect some tags or disable Force RAW.'
                }), 400

        # Read data
        df = data_service.read_parquet_data(start_date, end_date, tags, max_points=MAX_CHART_DATA_POINTS, force_raw=force_raw)
        
        if df.empty:
            return jsonify({'success': True, 'data': [], 'count': 0})

        # _safe_records handles NaN/Inf/numpy types → JSON-safe (pandas-2.x safe)
        # NOTE: do NOT call pd.to_numeric here — errors='ignore' removed in pandas 2.2
        meta = getattr(data_service, '_last_query_meta', {}) or {}
        result = {
            'success': True,
            'data': _safe_records(df),
            'count': len(df),
            'query_mode': meta.get('query_mode', 'unknown'),
            'bucket_seconds': meta.get('bucket_seconds'),
            'est_rows_db': meta.get('est_rows_db'),
            'sampled': meta.get('sampled', False),
            'elapsed_ms': meta.get('elapsed_ms', 0),
        }

        return jsonify(result)
        
    except Exception as e:
        import traceback as _tb
        _trace = _tb.format_exc()
        import logging; logging.getLogger(__name__).error("[/api/data] CRASH:\n%s", _trace)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/summary')
def get_summary():
    """Get data summary for date range"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        summary = data_service.get_data_summary(start_date, end_date)
        return jsonify({'success': True, 'summary': summary})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/csv')
def export_csv():
    """Export data to CSV"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        tags_param = request.args.get('tags')
        
        tags = json.loads(tags_param) if tags_param else None
        
        csv_data = data_service.export_to_csv(start_date, end_date, tags)
        
        if not csv_data:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        # Create filename with date range
        filename = f"historical_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            io.BytesIO(csv_data.encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/excel')
def export_excel():
    """Export data to Excel"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        tags_param = request.args.get('tags')
        
        tags = json.loads(tags_param) if tags_param else None
        
        excel_data = data_service.export_to_excel(start_date, end_date, tags)
        
        if not excel_data:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        # Create filename with date range
        filename = f"historical_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            io.BytesIO(excel_data),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config')
def get_config():
    """Get current configuration including trends config"""
    return jsonify({
        'success': True,
        'config': {
            'data_directory': config.get_data_directory(),
            'backup_directory': config.get_backup_directory()
        },
        **trends_config  # Merge trends config into response
    })

# =====================================================
# INTERPOLATION CACHE ENDPOINTS
# =====================================================

@app.route('/api/interpolation/create', methods=['POST'])
def create_interpolation_cache():
    """
    Create interpolation cache for missing data
    NEVER modifies original parquet file
    """
    try:
        data = request.get_json()
        
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        tags = data.get('tags')
        method = data.get('method', 'linear')
        
        # Read original data (READ-ONLY)
        df = data_service.read_parquet_data(start_date, end_date, tags)
        
        if df.empty:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        # Create interpolation cache (does NOT modify original)
        result = interpolation_service.create_interpolated_dataset(
            original_data=df,
            tags=tags,
            method=method
        )
        
        return jsonify({
            'success': True,
            'message': 'Interpolation cache created',
            'interpolated_count': result['interpolated_count'],
            'log': result['log'],
            'cache_file': result['cache_file']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/interpolation/data')
def get_interpolated_data():
    """
    Get data with optional interpolation applied
    Original parquet is NEVER modified
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        tags_param = request.args.get('tags')
        use_interpolated = request.args.get('use_interpolated', 'false').lower() == 'true'
        
        tags = json.loads(tags_param) if tags_param else None
        
        # Read original data (READ-ONLY)
        df = data_service.read_parquet_data(start_date, end_date, tags)
        
        if df.empty:
            return jsonify({'success': True, 'data': [], 'count': 0})
        
        # Apply interpolation if requested (on COPY of data)
        if use_interpolated:
            df = interpolation_service.get_merged_data(df, use_interpolated=True)
        
        # Calculate statistics for each tag BEFORE converting NaN to None
        tag_stats = {}
        if tags:
            for tag in tags:
                if tag in df.columns and tag != 'Timestamp':
                    try:
                        # Filter out NaN/None values before calculating statistics
                        # Convert to numeric, coercing errors to NaN
                        valid_values = pd.to_numeric(df[tag], errors='coerce').dropna()
                        if len(valid_values) > 0:
                            tag_stats[tag] = {
                                'mean': float(valid_values.mean()),
                                'std': float(valid_values.std()),
                                'min': float(valid_values.min()),
                                'max': float(valid_values.max()),
                                'count': int(len(valid_values))
                            }
                        else:
                            tag_stats[tag] = {
                                'mean': None,
                                'std': None,
                                'min': None,
                                'max': None,
                                'count': 0
                            }
                    except Exception as e:
                        # If statistics calculation fails, set to None
                        tag_stats[tag] = {
                            'mean': None,
                            'std': None,
                            'min': None,
                            'max': None,
                            'count': 0
                        }
        
        # Replace NaN with None for valid JSON (AFTER statistics calculation)
        result = {
            'success': True,
            'data': _safe_records(df),
            'count': len(df),
            'interpolated': use_interpolated,
            'statistics': tag_stats
        }

        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analytics/boxplot')
def get_boxplot_data():
    """Calculate box plot statistics on server side"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        tags_param = request.args.get('tags')
        use_interpolated = request.args.get('use_interpolated', 'false').lower() == 'true'
        
        tags = json.loads(tags_param) if tags_param else None
        
        # Read data
        df = data_service.read_parquet_data(start_date, end_date, tags)
        
        if df.empty:
            return jsonify({'success': True, 'boxplot_data': [], 'count': 0})
        
        # Apply interpolation if requested
        if use_interpolated:
            df = interpolation_service.get_merged_data(df, use_interpolated=True)
        
        # Calculate box plot statistics for each tag
        boxplot_data = []
        if tags:
            for tag in tags:
                if tag in df.columns and tag != 'Timestamp':
                    # Convert to numeric and drop NaN
                    values = pd.to_numeric(df[tag], errors='coerce').dropna()
                    if len(values) > 0:
                        # Downsample if too many points (box plot doesn't need all data)
                        if len(values) > MAX_BOXPLOT_SAMPLES:
                            values = values.sample(n=MAX_BOXPLOT_SAMPLES, random_state=42)
                        
                        boxplot_data.append({
                            'tag': tag,
                            'values': values.tolist(),
                            'q1': float(values.quantile(0.25)),
                            'q2': float(values.quantile(0.5)),
                            'q3': float(values.quantile(0.75)),
                            'min': float(values.min()),
                            'max': float(values.max()),
                            'mean': float(values.mean()),
                            'std': float(values.std())
                        })
        
        return jsonify({
            'success': True,
            'boxplot_data': boxplot_data,
            'count': len(boxplot_data)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analytics/distribution')
def get_distribution_data():
    """Calculate distribution histogram on server side"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        tags_param = request.args.get('tags')
        use_interpolated = request.args.get('use_interpolated', 'false').lower() == 'true'
        bins = int(request.args.get('bins', 30))
        
        tags = json.loads(tags_param) if tags_param else None
        
        # Read data
        df = data_service.read_parquet_data(start_date, end_date, tags)
        
        if df.empty:
            return jsonify({'success': True, 'distribution_data': [], 'count': 0})
        
        # Apply interpolation if requested
        if use_interpolated:
            df = interpolation_service.get_merged_data(df, use_interpolated=True)
        
        # Calculate distribution for each tag
        distribution_data = []
        if tags:
            for tag in tags:
                if tag in df.columns and tag != 'Timestamp':
                    # Convert to numeric and drop NaN
                    values = pd.to_numeric(df[tag], errors='coerce').dropna()
                    if len(values) > 0:
                        # Downsample if too many points (histogram doesn't need all data)
                        if len(values) > MAX_DISTRIBUTION_SAMPLES:
                            values = values.sample(n=MAX_DISTRIBUTION_SAMPLES, random_state=42)
                        
                        # Calculate histogram
                        hist, bin_edges = np.histogram(values, bins=bins)
                        
                        # Calculate normal distribution curve
                        mean = float(values.mean())
                        std = float(values.std())
                        x_curve = np.linspace(float(values.min()), float(values.max()), 100)
                        y_curve = (len(values) * (bin_edges[1] - bin_edges[0]) / 
                                  (std * np.sqrt(2 * np.pi)) * 
                                  np.exp(-0.5 * ((x_curve - mean) / std) ** 2))
                        
                        distribution_data.append({
                            'tag': tag,
                            'values': values.tolist(),
                            'histogram': {
                                'counts': hist.tolist(),
                                'bin_edges': bin_edges.tolist()
                            },
                            'normal_curve': {
                                'x': x_curve.tolist(),
                                'y': y_curve.tolist()
                            },
                            'stats': {
                                'mean': mean,
                                'std': std,
                                'min': float(values.min()),
                                'max': float(values.max())
                            }
                        })
        
        return jsonify({
            'success': True,
            'distribution_data': distribution_data,
            'count': len(distribution_data)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/interpolation/stats')
def get_interpolation_stats():
    """Get interpolation cache statistics"""
    try:
        stats = interpolation_service.get_cache_statistics()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/interpolation/clear', methods=['POST'])
def clear_interpolation_cache():
    """Clear interpolation cache"""
    try:
        data = request.get_json()
        tags = data.get('tags') if data else None
        
        interpolation_service.clear_cache(tags)
        
        return jsonify({
            'success': True,
            'message': 'Cache cleared' if tags is None else f'Cache cleared for {len(tags)} tags'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/interpolation/report')
def get_interpolation_report():
    """Export detailed interpolation report"""
    try:
        output_file = config.get_data_directory() + '/interpolation_report.json'
        report = interpolation_service.export_interpolation_report(output_file)
        
        if report is None:
            return jsonify({'success': False, 'error': 'No interpolation cache found'}), 404
        
        return jsonify({'success': True, 'report': report})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================
# PREDICTIVE INTERPOLATION ENDPOINTS (ML Models)
# =====================================================

@app.route('/api/prediction/available_models')
def get_available_models():
    """Get list of available prediction models"""
    try:
        models = predictive_service.get_available_models()
        return jsonify({'success': True, 'models': models})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prediction/compare', methods=['POST'])
def compare_prediction_models():
    """Compare multiple models - ASYNC to prevent blocking"""
    try:
        data = request.get_json()
        
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        tag = data.get('tag')
        models = data.get('models')  # List of models to compare
        
        # Read original data
        df = data_service.read_parquet_data(start_date, end_date, [tag])
        
        if df.empty:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        # Create unique task ID
        task_id = f"task_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Initialize task status
        prediction_tasks[task_id] = {
            'status': 'running',
            'progress': 0,
            'results': None,
            'started': datetime.now().isoformat()
        }
        
        # Run comparison in background thread
        def run_comparison():
            try:
                result = predictive_service.compare_models(df, tag, models)
                prediction_tasks[task_id]['status'] = 'completed'
                prediction_tasks[task_id]['progress'] = 100
                prediction_tasks[task_id]['results'] = result
                prediction_tasks[task_id]['completed'] = datetime.now().isoformat()
            except Exception as e:
                prediction_tasks[task_id]['status'] = 'failed'
                prediction_tasks[task_id]['error'] = str(e)
        
        thread = threading.Thread(target=run_comparison)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Prediction comparison started (running in background)'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prediction/status/<task_id>')
def get_prediction_status(task_id):
    """Get status of async prediction task"""
    if task_id not in prediction_tasks:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    
    task = prediction_tasks[task_id]
    return jsonify({'success': True, 'task': task})

@app.route('/api/prediction/save', methods=['POST'])
def save_prediction():
    """Save user-confirmed prediction to cache"""
    try:
        data = request.get_json()
        
        predictions = data.get('predictions')
        model = data.get('model')
        tag = data.get('tag')
        user_confirmed = data.get('user_confirmed', False)
        
        if not user_confirmed:
            return jsonify({
                'success': False,
                'error': 'User confirmation required'
            }), 400
        
        result = predictive_service.save_predictions(
            predictions, model, tag, user_confirmed
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prediction/single', methods=['POST'])
def predict_single_model():
    """Run single model prediction - ASYNC"""
    try:
        data = request.get_json()
        
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        tag = data.get('tag')
        model = data.get('model', 'fft')
        
        df = data_service.read_parquet_data(start_date, end_date, [tag])
        
        if df.empty:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        task_id = f"task_{tag}_{model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        prediction_tasks[task_id] = {
            'status': 'running',
            'progress': 0,
            'results': None,
            'started': datetime.now().isoformat()
        }
        
        def run_prediction():
            try:
                result = predictive_service.predict_missing_data(df, tag, model)
                prediction_tasks[task_id]['status'] = 'completed'
                prediction_tasks[task_id]['progress'] = 100
                prediction_tasks[task_id]['results'] = result
                prediction_tasks[task_id]['completed'] = datetime.now().isoformat()
            except Exception as e:
                prediction_tasks[task_id]['status'] = 'failed'
                prediction_tasks[task_id]['error'] = str(e)
        
        thread = threading.Thread(target=run_prediction)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'{model.upper()} prediction started'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================
# DERIVED ANALYTICS MANAGEMENT ENDPOINTS
# =====================================================

@app.route('/api/derived/config')
def get_derived_config():
    """Get derived analytics configuration"""
    try:
        return jsonify({
            'success': True,
            'config': derived_manager.config
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/derived/storage_stats')
def get_storage_stats():
    """Get storage statistics for derived data"""
    try:
        stats = derived_manager.get_storage_statistics()
        return jsonify({'success': True, 'statistics': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/derived/load/<metric_type>/<date>')
def load_derived_metric(metric_type, date):
    """Load specific derived metric for date"""
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        df = derived_manager.load_derived_data(metric_type, date_obj)
        
        if df is None:
            return jsonify({
                'success': False,
                'error': 'Data not found',
                'available': False
            }), 404
        
        # Convert to JSON — replace NaN/Inf before dict conversion
        df = df.replace([np.nan, np.inf, -np.inf], None)
        data = df.to_dict('records')
        
        return jsonify({
            'success': True,
            'metric_type': metric_type,
            'date': date,
            'data': data,
            'row_count': len(df)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/derived/load_range/<metric_type>')
def load_derived_metric_range(metric_type):
    """Load derived metric for date range"""
    try:
        start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
        
        df = derived_manager.get_date_range_data(metric_type, start_date, end_date)
        
        if df is None:
            return jsonify({
                'success': False,
                'error': 'No data found for date range'
            }), 404
        
        # Convert to JSON — replace NaN/Inf before dict conversion
        df = df.replace([np.nan, np.inf, -np.inf], None)
        data = df.to_dict('records')
        
        return jsonify({
            'success': True,
            'metric_type': metric_type,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'data': data,
            'row_count': len(df)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/derived/check_cache/<metric_type>/<date>')
def check_cache_status(metric_type, date):
    """Check if cached data is valid or needs recalculation"""
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        
        # Get input files for this date
        input_files = data_service.get_files_for_date_range(
            date_obj.strftime('%Y-%m-%d'),
            date_obj.strftime('%Y-%m-%d')
        )
        
        should_recalc, reason = derived_manager.should_recalculate(
            metric_type, date_obj, input_files
        )
        
        return jsonify({
            'success': True,
            'metric_type': metric_type,
            'date': date,
            'should_recalculate': should_recalc,
            'reason': reason,
            'cached_file_exists': os.path.exists(
                derived_manager.get_derived_file_path(metric_type, date_obj)
            )
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/derived/cleanup', methods=['POST'])
def cleanup_old_derived_data():
    """Cleanup old derived data files"""
    try:
        data = request.get_json()
        retention_days = data.get('retention_days') if data else None
        
        removed_count = derived_manager.cleanup_old_data(retention_days)
        
        return jsonify({
            'success': True,
            'removed_files': removed_count,
            'message': f'Removed {removed_count} old files'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/derived/export_report')
def export_derived_report():
    """Export comprehensive configuration and statistics report"""
    try:
        report = derived_manager.export_configuration_report()
        return jsonify({'success': True, 'report': report})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/baseline/config', methods=['GET'])
def get_baseline_config():
    """Get complete baseline configuration or specific tag config"""
    try:
        tag = request.args.get('tag')
        
        if tag:
            # Return config for specific tag
            target = baseline_config.get_target_production(tag)
            baseline_perf = baseline_config.get_baseline_performance(tag)
            rated_capacity = baseline_config.get_rated_capacity(tag)
            tag_config = baseline_config.get_tag_config(tag)
            
            return jsonify({
                'success': True,
                'tag': tag,
                'target_production': target,
                'baseline_performance': baseline_perf,
                'rated_capacity': rated_capacity,
                'full_config': tag_config
            })
        else:
            # Return complete configuration
            return jsonify(baseline_config.config)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/baseline/config', methods=['POST'])
def update_baseline_config():
    """Update baseline configuration"""
    try:
        data = request.json
        tag = data.get('tag')
        
        if not tag:
            return jsonify({'success': False, 'error': 'Tag required'}), 400
        
        # Update user target if provided
        if 'target_production' in data:
            if data['target_production'] is None:
                baseline_config.clear_user_target(tag)
            else:
                baseline_config.set_user_target(tag, data['target_production'])
        
        # Update rated capacity if provided
        if 'rated_capacity' in data:
            baseline_config.set_rated_capacity(tag, data['rated_capacity'])
        
        # Update baseline performance if provided
        if 'baseline_performance' in data:
            baseline_config.set_baseline_performance(
                tag, 
                data['baseline_performance'],
                data.get('sample_size')
            )
        
        return jsonify({'success': True, 'message': 'Configuration updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/baseline/calculate', methods=['POST'])
def calculate_baseline():
    """Calculate adaptive baseline using Python backend"""
    try:
        from bi_engines.baseline_engine import AdaptiveBaselineEngine
        
        data = request.json
        df = pd.DataFrame(data['data'])
        tag = data['tag']
        config = data.get('config', {})
        
        # Convert all numeric columns to float (handle string values from JSON)
        for col in df.columns:
            if col != 'Timestamp':
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        engine = AdaptiveBaselineEngine(config)
        result = engine.calculate_adaptive_baseline(df, tag)
        
        if result is None:
            return jsonify({'success': False, 'error': 'Insufficient data'}), 400
            
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/efficiency/calculate', methods=['POST'])
def calculate_efficiency():
    """Calculate efficiency-adjusted expected production"""
    try:
        from bi_engines.efficiency_engine import EfficiencyAdjustmentEngine
        
        data = request.json
        # Handle both baseline_production (legacy) and baseline_value (new)
        baseline_production = float(data.get('baseline_production') or data.get('baseline_value', 0))
        current_conditions = data.get('current_conditions', {})
        parameters = data.get('parameters', {})
        
        # Convert current_conditions values to float
        current_conditions = {k: float(v) if v is not None else 0.0 for k, v in current_conditions.items()}
        
        engine = EfficiencyAdjustmentEngine({'influencing_parameters': parameters})
        result = engine.calculate_adjusted_expected(
            baseline_production, 
            current_conditions
        )
        
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/delta/calculate', methods=['POST'])
def calculate_weighted_delta():
    """Calculate weighted production delta"""
    try:
        from bi_engines.delta_scorer import WeightedDeltaScorer
        
        data = request.json
        actual = float(data['actual'])
        expected = float(data['expected'])
        metadata = data.get('metadata', data.get('operating_condition', {}))  # Accept both names
        timestamp = data.get('timestamp')
        config = data.get('config', {})
        
        engine = WeightedDeltaScorer(config)
        result = engine.calculate_weighted_delta(actual, expected, metadata, timestamp)
        
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/availability/calculate', methods=['POST'])
def calculate_availability():
    """Calculate availability-based production"""
    try:
        from bi_engines.availability_engine import AvailabilityProductionEngine
        
        data = request.json
        production_data = data.get('data')
        rated_capacity = float(data.get('rated_capacity')) if data.get('rated_capacity') else None
        load_col = data.get('load_col')  # optional explicit load column

        if production_data is None or rated_capacity is None:
            return jsonify({'success': False, 'error': 'Required fields: data, rated_capacity'}), 400

        # Build DataFrame
        df = pd.DataFrame(production_data)
        if df.empty:
            return jsonify({'success': False, 'error': 'No data rows provided'}), 400

        # Normalize timestamps
        if 'Timestamp' not in df.columns:
            return jsonify({'success': False, 'error': 'Timestamp column missing'}), 400
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df = df.dropna(subset=['Timestamp'])

        # Coerce numerics
        numeric_candidates = []
        for col in df.columns:
            if col == 'Timestamp':
                continue
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].notna().sum() > 0:
                numeric_candidates.append(col)

        # Infer load column if not supplied
        if not load_col:
            priority_names = ['Production', 'Load', 'MW', 'Power']
            load_col = next((p for p in priority_names if p in df.columns), None)
            if not load_col:
                # choose first numeric candidate
                load_col = numeric_candidates[0] if numeric_candidates else None

        if not load_col or load_col not in df.columns:
            return jsonify({'success': False, 'error': 'Unable to determine load column'}), 400

        engine = AvailabilityProductionEngine()
        result = engine.calculate_availability_production(
            df,
            load_col,
            rated_capacity,
            'Timestamp'
        )

        result['load_col_used'] = load_col
        result['success'] = True
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/influence/calculate', methods=['POST'])
def calculate_influence():
    """Compute multi-parameter influence map"""
    try:
        from bi_engines.influence_engine import InfluenceMapEngine
        
        data = request.json
        primary_tag = data['primary_tag']
        influencing_tags = data['influencing_tags']
        dataset = data['data']
        
        # Convert data to DataFrame and ensure numeric types
        df = pd.DataFrame(dataset)
        if df.empty:
            return jsonify({'success': False, 'error': 'No data rows provided'}), 400

        if 'Timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')

        # Coerce numeric for all non-timestamp columns
        for col in df.columns:
            if col != 'Timestamp':
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Validate presence of required tags
        missing = [t for t in [primary_tag] + influencing_tags if t not in df.columns]
        if missing:
            return jsonify({'success': False, 'error': f'Missing tags: {missing}'}), 400

        engine = InfluenceMapEngine()
        result = engine.compute_influence_map(df, primary_tag, influencing_tags)
        return jsonify({'success': True, 'influence_map': result, 'primary_tag': primary_tag, 'influencing_tags': influencing_tags})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/stability/calculate', methods=['POST'])
def calculate_stability():
    """Calculate performance stability index"""
    try:
        import numpy as np
        from bi_engines.stability_engine import StabilityIndexEngine
        
        data = request.json
        values = np.array(data['values'], dtype=float)
        
        engine = StabilityIndexEngine()
        result = engine.calculate_stability_index(values)
        
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/condition/score', methods=['POST'])
def score_condition():
    """Score parameter condition"""
    try:
        from bi_engines.condition_engine import ConditionScoringEngine
        
        data = request.json
        parameter = data.get('parameter', '')
        value = data.get('value')
        
        # Handle None/null values
        if value is None:
            return jsonify({'score': 50, 'color': 'yellow', 'status': 'Unknown', 'value': None, 'unit': 'Unknown', 'parameter': parameter})
        
        value = float(value)
        custom_thresholds = data.get('custom_thresholds')
        
        engine = ConditionScoringEngine()
        result = engine.score_condition(parameter, value, custom_thresholds)
        
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/loss/attribute', methods=['POST'])
def attribute_loss():
    """Attribute production loss to specific causes"""
    try:
        from bi_engines.loss_engine import LossAttributionEngine
        
        data = request.json
        
        # Handle different payload structures
        actual_production = data.get('actual_production', data.get('actual', 0))
        expected_production = data.get('expected_production', data.get('expected', 0))
        influence_map = data.get('influence_map', {})
        current_conditions = data.get('current_conditions', {})
        
        actual_production = float(actual_production) if actual_production is not None else 0.0
        expected_production = float(expected_production) if expected_production is not None else 0.0
        
        # Convert current_conditions values to float
        current_conditions = {k: float(v) if v is not None else 0.0 for k, v in current_conditions.items()}
        
        engine = LossAttributionEngine()
        result = engine.attribute_loss(
            actual_production,
            expected_production,
            influence_map,
            current_conditions
        )
        
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/analytics/correlation', methods=['POST'])
def calculate_correlation():
    """Calculate Pearson correlation between two arrays"""
    try:
        import numpy as np
        from scipy.stats import pearsonr
        
        data = request.json
        arr1 = np.array(data['arr1'])
        arr2 = np.array(data['arr2'])
        
        if len(arr1) != len(arr2) or len(arr1) == 0:
            return jsonify({'correlation': 0, 'p_value': 1.0})
        
        # Remove NaN pairs
        mask = ~(np.isnan(arr1) | np.isnan(arr2))
        clean_arr1 = arr1[mask]
        clean_arr2 = arr2[mask]
        
        if len(clean_arr1) < 2:
            return jsonify({'correlation': 0, 'p_value': 1.0})
        
        corr, p_value = pearsonr(clean_arr1, clean_arr2)
        
        return jsonify({
            'correlation': float(corr),
            'p_value': float(p_value),
            'sample_size': int(len(clean_arr1))
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/analytics/correlation_matrix', methods=['POST'])
def calculate_correlation_matrix():
    """Calculate correlation matrix for multiple tags"""
    try:
        import numpy as np
        import pandas as pd
        
        data = request.json
        dataset = pd.DataFrame(data['data'])
        tags = data['tags']
        
        # Extract only numeric columns that exist
        available_tags = [tag for tag in tags if tag in dataset.columns]
        if len(available_tags) == 0:
            return jsonify({'matrix': {}, 'tags': []})
        
        # Calculate correlation matrix using pandas
        numeric_data = dataset[available_tags].select_dtypes(include=[np.number])
        corr_matrix = numeric_data.corr()
        
        # Convert to nested dict format
        result = {}
        for tag1 in available_tags:
            result[tag1] = {}
            for tag2 in available_tags:
                if tag1 in corr_matrix.index and tag2 in corr_matrix.columns:
                    corr_val = corr_matrix.loc[tag1, tag2]
                    result[tag1][tag2] = float(corr_val) if not np.isnan(corr_val) else 0.0
                else:
                    result[tag1][tag2] = 0.0
        
        return jsonify({
            'matrix': result,
            'tags': available_tags
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/analytics/statistics', methods=['POST'])
def calculate_statistics():
    """Calculate comprehensive statistics for tags"""
    try:
        import numpy as np
        import pandas as pd
        
        data = request.json
        dataset = pd.DataFrame(data['data'])
        tags = data['tags']
        
        stats_result = {}
        
        for tag in tags:
            if tag not in dataset.columns:
                continue
                
            values = dataset[tag].dropna()
            
            if len(values) == 0:
                stats_result[tag] = {
                    'mean': 0, 'median': 0, 'min': 0, 'max': 0,
                    'std_dev': 0, 'variance': 0, 'q1': 0, 'q3': 0,
                    'count': 0, 'cv': 0
                }
                continue
            
            stats_result[tag] = {
                'mean': float(values.mean()),
                'median': float(values.median()),
                'min': float(values.min()),
                'max': float(values.max()),
                'std_dev': float(values.std()),
                'variance': float(values.var()),
                'q1': float(values.quantile(0.25)),
                'q3': float(values.quantile(0.75)),
                'count': int(len(values)),
                'cv': float((values.std() / values.mean() * 100) if values.mean() != 0 else 0)
            }
        
        return jsonify(stats_result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/industrial/operating_bands', methods=['POST'])
def calculate_operating_bands():
    """Calculate default operating bands from statistical analysis"""
    try:
        import numpy as np
        import pandas as pd
        
        data = request.json
        dataset = pd.DataFrame(data['data'])
        tag = data['tag']
        
        if tag not in dataset.columns:
            return jsonify({'error': f'Tag {tag} not found'}), 404
        
        values = dataset[tag].dropna()
        
        if len(values) == 0:
            return jsonify({'error': 'No valid data'}), 400
        
        mean = float(values.mean())
        std_dev = float(values.std())
        sorted_vals = values.sort_values()
        
        # Get band width from config (default 2 for ±2σ bands)
        band_config = trends_config.get('OperatingBands', {})
        band_width = band_config.get('DefaultBandWidth', 2)
        
        return jsonify({
            'veryLow': float(sorted_vals.iloc[0]),
            'low': mean - band_width * std_dev,
            'normalMin': mean - std_dev,
            'normalMax': mean + std_dev,
            'high': mean + band_width * std_dev,
            'veryHigh': float(sorted_vals.iloc[-1]),
            'critical': mean + (band_width + 1) * std_dev,
            'mean': mean,
            'std_dev': std_dev
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/industrial/shift_stats', methods=['POST'])
def calculate_shift_stats():
    """Calculate shift statistics"""
    try:
        import numpy as np
        import pandas as pd
        
        data = request.json
        dataset = pd.DataFrame(data['data'])
        tag = data['tag']
        shift_start = pd.to_datetime(data['shift_start'])
        shift_end = pd.to_datetime(data['shift_end'])
        
        if tag not in dataset.columns or 'Timestamp' not in dataset.columns:
            return jsonify({'error': 'Invalid data structure'}), 400
        
        dataset['Timestamp'] = pd.to_datetime(dataset['Timestamp'])
        shift_data = dataset[(dataset['Timestamp'] >= shift_start) & (dataset['Timestamp'] <= shift_end)]
        
        if len(shift_data) == 0:
            return jsonify({'error': 'No data in shift period'}), 400
        
        values = shift_data[tag].dropna()
        
        # Calculate trend (first half vs second half)
        mid = len(values) // 2
        first_half_mean = float(values.iloc[:mid].mean()) if mid > 0 else 0
        second_half_mean = float(values.iloc[mid:].mean()) if mid > 0 else 0
        trend_score = second_half_mean - first_half_mean
        
        return jsonify({
            'mean': float(values.mean()),
            'min': float(values.min()),
            'max': float(values.max()),
            'std_dev': float(values.std()),
            'trend_score': trend_score,
            'count': int(len(values)),
            'duration_hours': float((shift_end - shift_start).total_seconds() / 3600)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/industrial/health_scores', methods=['POST'])
def calculate_health_scores():
    """Calculate equipment health scores"""
    try:
        import numpy as np
        import pandas as pd
        
        data = request.json
        dataset = pd.DataFrame(data['data'])
        tag = data['tag']
        
        if tag not in dataset.columns:
            return jsonify({'error': f'Tag {tag} not found'}), 404
        
        values = dataset[tag].dropna()
        
        if len(values) < 2:
            return jsonify({'error': 'Insufficient data'}), 400
        
        mean = values.mean()
        std_dev = values.std()
        
        # Coefficient of variation
        cv = (std_dev / mean * 100) if mean != 0 else 0
        
        # Outlier detection (3-sigma)
        outliers = values[(values < mean - 3*std_dev) | (values > mean + 3*std_dev)]
        outlier_percentage = len(outliers) / len(values) * 100
        
        # Stability score (lower CV = better)
        stability_score = max(0, min(100, 100 - cv))
        
        # Overall health score
        health_score = stability_score * (1 - outlier_percentage/100)
        
        return jsonify({
            'health_score': float(health_score),
            'stability_score': float(stability_score),
            'cv': float(cv),
            'outlier_percentage': float(outlier_percentage),
            'rating': 'Excellent' if health_score > 90 else 'Good' if health_score > 75 else 'Fair' if health_score > 50 else 'Poor'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================
# DOWNTIME TRACKING & MTBF/MTTR APIs
# =====================================================

@app.route('/api/downtime/detect', methods=['POST'])
def detect_downtimes():
    """Detect downtime events from production data"""
    try:
        data = request.json
        start_date = pd.to_datetime(data['start_date'])
        end_date = pd.to_datetime(data['end_date'])
        production_tag = data.get('production_tag', 'TURBINE_LOADMW')
        
        # Load production data
        df = data_service.read_parquet_data(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            tags=[production_tag]
        )
        
        if len(df) == 0:
            return jsonify({'success': True, 'downtimes': [], 'message': 'No data available'})
        
        # Detect downtimes
        downtimes = downtime_service.detect_downtimes(df, production_tag)
        
        # Detect abnormal parameters for each downtime
        for downtime in downtimes:
            if downtime['start_timestamp']:
                abnormal_params = downtime_service.detect_abnormal_parameters(
                    df, 
                    downtime['start_timestamp'],
                    window_minutes=30
                )
                downtime['abnormal_parameters'] = json.dumps(abnormal_params) if abnormal_params else None
                
                # Save downtime event
                downtime_service.save_downtime_event(downtime)
        
        # Convert datetime objects to strings for JSON
        for dt in downtimes:
            dt['start_timestamp'] = dt['start_timestamp'].isoformat() if dt['start_timestamp'] else None
            dt['end_timestamp'] = dt['end_timestamp'].isoformat() if dt['end_timestamp'] else None
            dt['created_at'] = dt['created_at'].isoformat()
            dt['updated_at'] = dt['updated_at'].isoformat()
        
        return jsonify({
            'success': True,
            'downtimes': downtimes,
            'count': len(downtimes)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/downtime/mtbf-mttr', methods=['POST'])
def calculate_mtbf_mttr():
    """Calculate MTBF and MTTR for a period"""
    try:
        data = request.json
        start_date = pd.to_datetime(data['start_date'])
        end_date = pd.to_datetime(data['end_date'])
        production_tag = data.get('production_tag', 'TURBINE_LOADMW')
        
        # Calculate MTBF/MTTR
        result = downtime_service.calculate_mtbf_mttr(start_date, end_date, production_tag)
        
        # Convert datetime objects to strings
        result['period_start'] = result['period_start'].isoformat()
        result['period_end'] = result['period_end'].isoformat()
        
        for dt in result['downtime_events']:
            dt['start_timestamp'] = dt['start_timestamp'].isoformat() if isinstance(dt['start_timestamp'], datetime) else dt['start_timestamp']
            dt['end_timestamp'] = dt['end_timestamp'].isoformat() if isinstance(dt['end_timestamp'], datetime) and dt['end_timestamp'] else None
            dt['created_at'] = dt['created_at'].isoformat() if isinstance(dt['created_at'], datetime) else dt['created_at']
            dt['updated_at'] = dt['updated_at'].isoformat() if isinstance(dt['updated_at'], datetime) else dt['updated_at']
        
        return jsonify({
            'success': True,
            'mtbf_mttr': result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/downtime/update-reason', methods=['POST'])
def update_downtime_reason():
    """Update failure reason for a downtime event"""
    try:
        data = request.json
        downtime_id = data['downtime_id']
        failure_category = data['failure_category']
        failure_reason = data['failure_reason']
        root_cause = data.get('root_cause')
        corrective_action = data.get('corrective_action')
        created_by = data.get('created_by', 'User')
        
        success = downtime_service.update_failure_reason(
            downtime_id=downtime_id,
            failure_category=failure_category,
            failure_reason=failure_reason,
            root_cause=root_cause,
            corrective_action=corrective_action,
            created_by=created_by
        )
        
        return jsonify({
            'success': success,
            'message': 'Failure reason updated' if success else 'Downtime event not found'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/downtime/list', methods=['GET'])
def list_downtimes():
    """Get list of downtime events for a period"""
    try:
        start_date = pd.to_datetime(request.args.get('start_date'))
        end_date = pd.to_datetime(request.args.get('end_date'))
        production_tag = request.args.get('production_tag', 'TURBINE_LOADMW')
        
        downtimes = downtime_service.load_downtime_records(start_date, end_date, production_tag)
        
        # Convert datetime objects
        for dt in downtimes:
            if isinstance(dt['start_timestamp'], datetime):
                dt['start_timestamp'] = dt['start_timestamp'].isoformat()
            if dt['end_timestamp'] and isinstance(dt['end_timestamp'], datetime):
                dt['end_timestamp'] = dt['end_timestamp'].isoformat()
            if isinstance(dt['created_at'], datetime):
                dt['created_at'] = dt['created_at'].isoformat()
            if isinstance(dt['updated_at'], datetime):
                dt['updated_at'] = dt['updated_at'].isoformat()
        
        return jsonify({
            'success': True,
            'downtimes': downtimes,
            'count': len(downtimes)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/downtime/categories', methods=['GET'])
def get_failure_categories():
    """Get list of failure categories"""
    try:
        categories = downtime_service.mtbf_config.get('failure_categories', [])
        return jsonify({
            'success': True,
            'categories': categories
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================
# SIMPLE DAILY BI ENDPOINT (Production, Utilization, OEE, SCC)
# =====================================================

@app.route('/simple_bi')
def simple_bi_page():
    """Render simplified BI dashboard (daily metrics only)"""
    # Force cache bust with timestamp
    import time
    return render_template('simple_bi.html', v=int(time.time()))

@app.route('/api/bi/simple_daily_metrics')
def simple_daily_metrics():
    """Return daily simplified BI metrics for selected period.

    Query Params:
        start_date (YYYY-MM-DD)
        end_date   (YYYY-MM-DD)
        rated_capacity (optional override, MW)
        production_tag (default TURBINE_LOADMW)
        coal_tag (default TOTAL_COAL_FLOW)
        steam_tag (optional MAIN_STEAM_FLOWTPH)

    Notes:
        - Coal flow assumed instantaneous TPH (tons/hour)
        - SCC (kg/kWh) = coal_tph / avg_load_mw  (since coal_tph*1000 kg/h / (avg_load_mw*1000 kW))
        - Availability threshold: load > 5% rated_capacity
        - generation_mwh uses hours_covered (derived from sampling) * avg_load_mw / 1 (since MW * h = MWh)
        - Deltas: vs overall period mean & rated capacity
    """
    try:
        # Parse inputs
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        production_tag = request.args.get('production_tag', 'TURBINE_LOADMW')
        coal_tag = request.args.get('coal_tag', 'TOTAL_COAL_FLOW')
        steam_tag = request.args.get('steam_tag', 'MAIN_STEAM_FLOWTPH')
        rated_capacity_override = request.args.get('rated_capacity')

        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'error': 'start_date and end_date are required'}), 400

        start_date = pd.to_datetime(start_date_str)
        end_date = pd.to_datetime(end_date_str)
        if end_date < start_date:
            return jsonify({'success': False, 'error': 'end_date must be >= start_date'}), 400

        days_requested = (end_date - start_date).days + 1
        MAX_DAYS_ALLOWED = 366
        if days_requested > MAX_DAYS_ALLOWED:
            return jsonify({
                'success': False,
                'error': f'Date range too large: {days_requested} days requested. '
                         f'Maximum allowed is {MAX_DAYS_ALLOWED} days per query. '
                         f'Please split the request into smaller date ranges.'
            }), 400

        # Attempt rated capacity from baseline config if not overridden
        rated_capacity = None
        if rated_capacity_override:
            try:
                rated_capacity = float(rated_capacity_override)
            except:
                return jsonify({'success': False, 'error': 'Invalid rated_capacity value'}), 400
        else:
            rated_capacity = baseline_config.get_rated_capacity(production_tag)

        if rated_capacity is None:
            return jsonify({'success': False, 'error': f'Rated capacity not found for tag {production_tag}. Provide rated_capacity.'}), 400

        # Read only required tags
        tags = [production_tag, coal_tag]
        if steam_tag:
            tags.append(steam_tag)
        df = data_service.read_parquet_data(start_date_str, end_date_str, tags)

        if df.empty:
            return jsonify({'success': True, 'groups': [], 'overall_mean_load_mw': None, 'rated_capacity_mw': rated_capacity, 'message': 'No data in range',
                            'actual_data_start': None, 'actual_data_end': None})

        # Determine actual data boundaries (for UI warning when range has gaps)
        actual_data_start = None
        actual_data_end   = None
        try:
            ts_col = pd.to_datetime(df['Timestamp'])
            if not ts_col.isna().all():
                actual_data_start = ts_col.min().strftime('%Y-%m-%d')
                actual_data_end   = ts_col.max().strftime('%Y-%m-%d')
        except Exception:
            pass

        # Ensure Timestamp column is datetime
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df = df.sort_values('Timestamp')

        # Validate required production tag exists
        if production_tag not in df.columns:
            return jsonify({
                'success': True,
                'rated_capacity_mw': rated_capacity,
                'overall_mean_load_mw': None,
                'sampling_minutes': None,
                'groups': [],
                'production_tag': production_tag,
                'coal_tag': coal_tag,
                'steam_tag': steam_tag,
                'availability_threshold_mw': round(rated_capacity * 0.05, 3),
                'message': f'Production tag {production_tag} not found in dataset'
            })

        # Convert numeric columns
        for col in [production_tag, coal_tag, steam_tag]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Overall period mean load
        overall_mean_load = df[production_tag].dropna().mean()

        # Derive effective sampling interval (minutes) using median diff
        ts_diffs = df['Timestamp'].diff().dropna().dt.total_seconds() / 60.0
        sampling_minutes = ts_diffs.median() if len(ts_diffs) > 0 else 1.0
        sampling_hours = sampling_minutes / 60.0

        # Group by calendar day
        df['Day'] = df['Timestamp'].dt.date
        daily_groups = []

        availability_threshold = rated_capacity * 0.05

        for day, day_df in df.groupby('Day'):
            day_df_valid = day_df.dropna(subset=[production_tag])
            if day_df_valid.empty:
                continue

            avg_load = day_df_valid[production_tag].mean()

            # Hours covered based on count * sampling interval (simpler than min/max span if gaps exist)
            sample_count = len(day_df_valid)
            hours_covered = sample_count * sampling_hours

            # Generation MWh (adjust for partial coverage)
            generation_mwh = avg_load * hours_covered

            # Availability: proportion of samples above threshold * (sampling interval converts to hours)
            above_threshold_samples = day_df_valid[day_df_valid[production_tag] > availability_threshold]
            availability_hours = len(above_threshold_samples) * sampling_hours
            availability_pct = (availability_hours / hours_covered * 100.0) if hours_covered > 0 else None

            performance_pct = (generation_mwh / (rated_capacity * hours_covered) * 100.0) if hours_covered > 0 else None

            # Fixed average quality from config
            quality_pct = SIMPLE_BI_QUALITY_DEFAULT

            oee_pct = None
            if performance_pct is not None and availability_pct is not None and quality_pct is not None:
                oee_pct = (performance_pct * availability_pct * quality_pct) / 10000.0

            coal_rate_tph = day_df[coal_tag].dropna().mean() if coal_tag in day_df.columns else None
            scc_kg_per_kwh = None
            if coal_rate_tph is not None and avg_load and avg_load != 0:
                # coal_tph / avg_load_mw  (kg/kWh) because both scaled by 1000
                scc_kg_per_kwh = coal_rate_tph / avg_load

            steam_flow_tph = day_df[steam_tag].dropna().mean() if steam_tag in day_df.columns else None

            def _safe(v, decimals=3):
                """Round and convert to None if NaN/Inf – prevents invalid JSON."""
                if v is None:
                    return None
                try:
                    import math
                    f = float(v)
                    if math.isnan(f) or math.isinf(f):
                        return None
                    return round(f, decimals)
                except (TypeError, ValueError):
                    return None

            daily_groups.append({
                'label': str(day),
                'start': f"{day}T00:00:00",
                'end': f"{day}T23:59:59",
                'sample_count': int(sample_count),
                'hours_covered': _safe(hours_covered, 3),
                'avg_load_mw': _safe(avg_load, 3),
                'generation_mwh': _safe(generation_mwh, 3),
                'utilization_pct': _safe(avg_load / rated_capacity * 100.0, 3) if rated_capacity else None,
                'availability_pct': _safe(availability_pct, 3),
                'performance_pct': _safe(performance_pct, 3),
                'quality_pct': _safe(quality_pct, 3),
                'oee_pct': _safe(oee_pct, 3),
                'coal_rate_tph': _safe(coal_rate_tph, 3),
                'steam_flow_tph': _safe(steam_flow_tph, 3),
                'scc_kg_per_kwh': _safe(scc_kg_per_kwh, 5),
                'delta_from_mean_mw': _safe(avg_load - overall_mean_load, 3) if overall_mean_load is not None else None,
                'delta_from_rated_mw': _safe(avg_load - rated_capacity, 3) if rated_capacity is not None else None
            })

        import math
        def _sf(v, d=3):
            """Top-level safe float — NaN/Inf → None."""
            if v is None: return None
            try:
                f = float(v)
                return None if (math.isnan(f) or math.isinf(f)) else round(f, d)
            except (TypeError, ValueError):
                return None

        return jsonify({
            'success': True,
            'rated_capacity_mw': _sf(rated_capacity, 3),
            'overall_mean_load_mw': _sf(overall_mean_load, 3),
            'sampling_minutes': _sf(sampling_minutes, 4),
            'groups': daily_groups,
            'production_tag': production_tag,
            'coal_tag': coal_tag,
            'steam_tag': steam_tag,
            'availability_threshold_mw': _sf(availability_threshold, 3),
            'quality_default_pct': SIMPLE_BI_QUALITY_DEFAULT,
            'actual_data_start': actual_data_start,
            'actual_data_end': actual_data_end,
            'days_requested': days_requested
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    import pandas as pd
    import os
    print("=" * 60)
    print("Historical Trends Viewer - Python Service")
    print("=" * 60)
    print(f"Data Directory: {config.get_data_directory()}")
    print(f"Backup Directory: {config.get_backup_directory()}")
    print(f"Derived Data: {derived_manager.derived_data_dir}")
    print(f"Downtime Tracking: {downtime_service.storage_dir}")
    print("=" * 60)
    print("Starting server on http://192.168.29.47:5002")
    print("=" * 60)
    app.run(host='0.0.0.0', port=6004, debug=False, threaded=True, use_reloader=False)
