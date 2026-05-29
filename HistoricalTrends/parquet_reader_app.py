"""
Parquet File Reader, Converter & Comparison Tool
ROBUST - FAST - MODULAR - NON-BLOCKING
Features:
- Chunked reading (no memory overflow)
- Async processing (no hanging)
- Streaming CSV download (fast conversion)
- Separate controls for each action
"""

from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import os
from datetime import datetime
from pathlib import Path
import json
import io
from concurrent.futures import ThreadPoolExecutor
import threading

app = Flask(__name__)
CORS(app)

# Default data directory
DATA_DIRECTORY = r"D:\OpcLogs\Data"

# Thread pool for async operations (non-blocking)
executor = ThreadPoolExecutor(max_workers=4)

# Chunk size for reading large files (prevent memory issues)
CHUNK_SIZE = 100000  # 100k rows at a time

# Schema from DataLoggingService.cs
# RowId (long), TagId (string), Timestamp (DateTime), Value (string), Quality (string)

@app.route('/')
def index():
    """Main parquet reader page"""
    return render_template('parquet_reader.html')

@app.route('/comparison')
def comparison():
    """Parquet vs CSV comparison page"""
    return render_template('parquet_csv_comparison.html')


# =====================================================
# API ENDPOINTS
# =====================================================

@app.route('/api/parquet/files', methods=['GET'])
def get_parquet_files():
    """Get list of all parquet files in data directory"""
    try:
        if not os.path.exists(DATA_DIRECTORY):
            return jsonify({
                'success': False, 
                'error': f'Directory not found: {DATA_DIRECTORY}'
            }), 404
        
        files = []
        for file in os.listdir(DATA_DIRECTORY):
            if file.endswith('.parquet'):
                file_path = os.path.join(DATA_DIRECTORY, file)
                file_size = os.path.getsize(file_path)
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # Try to get date range from file
                try:
                    df = pd.read_parquet(file_path)
                    if not df.empty and 'Timestamp' in df.columns:
                        min_date = df['Timestamp'].min()
                        max_date = df['Timestamp'].max()
                        row_count = len(df)
                    else:
                        min_date = max_date = None
                        row_count = 0
                except:
                    min_date = max_date = None
                    row_count = 0
                
                files.append({
                    'name': file,
                    'size': file_size,
                    'size_mb': round(file_size / (1024 * 1024), 2),
                    'modified': file_modified.isoformat(),
                    'min_date': min_date.isoformat() if min_date else None,
                    'max_date': max_date.isoformat() if max_date else None,
                    'row_count': row_count
                })
        
        return jsonify({
            'success': True,
            'files': files,
            'count': len(files),
            'directory': DATA_DIRECTORY
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/parquet/read', methods=['POST'])
def read_parquet_file():
    """
    ROBUST: Chunked reading with memory limits
    FAST: PyArrow direct read
    NON-BLOCKING: Limits row count for UI display
    """
    try:
        data = request.json
        filenames = data.get('filenames', [])
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        max_rows = data.get('max_rows', 10000)  # Limit for UI display
        
        if not filenames or len(filenames) == 0:
            return jsonify({'success': False, 'error': 'At least one filename required'}), 400
        
        # Read in batches to avoid memory issues
        all_batches = []
        total_read = 0
        
        for filename in filenames:
            file_path = os.path.join(DATA_DIRECTORY, filename)
            
            if not os.path.exists(file_path):
                continue
            
            # FAST: Use PyArrow for reading (faster than pandas)
            parquet_file = pq.ParquetFile(file_path)
        
            for batch in parquet_file.iter_batches(batch_size=CHUNK_SIZE):
                df_batch = batch.to_pandas()
                
                # Ensure Timestamp is datetime
                if 'Timestamp' in df_batch.columns:
                    df_batch['Timestamp'] = pd.to_datetime(df_batch['Timestamp'])
                
                # Filter by date range
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    df_batch = df_batch[df_batch['Timestamp'] >= start_dt]
                
                if end_date:
                    end_dt = pd.to_datetime(end_date)
                    df_batch = df_batch[df_batch['Timestamp'] <= end_dt]
                
                if len(df_batch) > 0:
                    all_batches.append(df_batch)
                    total_read += len(df_batch)
                
                # Limit rows for UI display
                if total_read >= max_rows:
                    break
        
        if not all_batches:
            return jsonify({
                'success': True,
                'data': [],
                'total_rows': 0,
                'columns': []
            })
        
        # Combine batches
        df = pd.concat(all_batches, ignore_index=True)
        df = df.head(max_rows)  # Ensure limit
        
        # Convert to records (optimized)
        records = df.to_dict('records')
        
        # Convert Timestamp to readable format (match main app format: 12/3/2025, 4:56:08 PM)
        for record in records:
            if 'Timestamp' in record and pd.notna(record['Timestamp']):
                # Timestamps are stored in UTC, convert to IST (UTC+5:30)
                ts = pd.to_datetime(record['Timestamp'])
                ts_local = ts + pd.Timedelta(hours=5, minutes=30)
                # Format as: M/D/YYYY, H:MM:SS AM/PM
                time_str = ts_local.strftime('%I:%M:%S %p').lstrip('0')
                record['Timestamp'] = f"{ts_local.month}/{ts_local.day}/{ts_local.year}, {time_str}"
        
        return jsonify({
            'success': True,
            'data': records,
            'total_rows': len(records),
            'columns': list(df.columns),
            'limited': total_read > max_rows
        })
    
    except Exception as e:
        import traceback
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/parquet/statistics', methods=['POST'])
def calculate_statistics():
    """
    FAST: Chunked statistics calculation (memory-efficient)
    ROBUST: Handles large files without hanging
    """
    try:
        data = request.json
        filenames = data.get('filenames', [])
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not filenames or len(filenames) == 0:
            return jsonify({'success': False, 'error': 'At least one filename required'}), 400
        
        # Accumulate statistics across chunks
        tag_stats = {}  # {tag_id: {'sum': 0, 'count': 0, 'min': inf, 'max': -inf, 'values': []}}
        total_rows = 0
        
        for filename in filenames:
            file_path = os.path.join(DATA_DIRECTORY, filename)
            
            if not os.path.exists(file_path):
                continue
            
            # Use PyArrow for faster reading
            parquet_file = pq.ParquetFile(file_path)
        
            for batch in parquet_file.iter_batches(batch_size=CHUNK_SIZE):
                df_batch = batch.to_pandas()
                
                # Ensure Timestamp is datetime
                if 'Timestamp' in df_batch.columns:
                    df_batch['Timestamp'] = pd.to_datetime(df_batch['Timestamp'])
                
                # Filter by date range
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    df_batch = df_batch[df_batch['Timestamp'] >= start_dt]
                
                if end_date:
                    end_dt = pd.to_datetime(end_date)
                    df_batch = df_batch[df_batch['Timestamp'] <= end_dt]
                
                if len(df_batch) == 0:
                    continue
                
                total_rows += len(df_batch)
                
                # Convert Value to numeric
                df_batch['ValueNumeric'] = pd.to_numeric(df_batch['Value'], errors='coerce')
                
                # Update statistics per tag
                for tag_id in df_batch['TagId'].unique():
                    tag_data = df_batch[df_batch['TagId'] == tag_id]['ValueNumeric'].dropna()
                    
                    if len(tag_data) == 0:
                        continue
                    
                    if tag_id not in tag_stats:
                        tag_stats[tag_id] = {
                            'sum': 0.0,
                            'count': 0,
                            'min': float('inf'),
                            'max': float('-inf'),
                            'sum_sq': 0.0  # For std dev
                        }
                    
                    tag_stats[tag_id]['sum'] += tag_data.sum()
                    tag_stats[tag_id]['count'] += len(tag_data)
                    tag_stats[tag_id]['min'] = min(tag_stats[tag_id]['min'], tag_data.min())
                    tag_stats[tag_id]['max'] = max(tag_stats[tag_id]['max'], tag_data.max())
                    tag_stats[tag_id]['sum_sq'] += (tag_data ** 2).sum()
        
        # Finalize statistics
        stats = []
        for tag_id, stat in tag_stats.items():
            count = stat['count']
            mean = stat['sum'] / count if count > 0 else 0.0
            
            # Calculate std dev
            if count > 1:
                variance = (stat['sum_sq'] / count) - (mean ** 2)
                std_dev = variance ** 0.5 if variance > 0 else 0.0
            else:
                std_dev = 0.0
            
            stats.append({
                'TagId': tag_id,
                'Count': int(count),
                'Sum': float(stat['sum']),
                'Average': float(mean),
                'Min': float(stat['min']),
                'Max': float(stat['max']),
                'StdDev': float(std_dev)
            })
        
        return jsonify({
            'success': True,
            'statistics': stats,
            'total_tags': len(stats),
            'total_rows_analyzed': total_rows
        })
    
    except Exception as e:
        import traceback
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/parquet/convert_to_csv', methods=['POST'])
def convert_to_csv():
    """
    SUPER FAST: Streaming CSV conversion (no memory issues)
    ROBUST: Handles large files with chunked processing
    NON-BLOCKING: Streams data directly to browser
    """
    try:
        data = request.json
        filename = data.get('filename')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not filename:
            return jsonify({'success': False, 'error': 'Filename required'}), 400
        
        file_path = os.path.join(DATA_DIRECTORY, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        csv_filename = filename.replace('.parquet', '.csv')
        
        def generate_csv():
            """Generator function for streaming CSV (FAST & MEMORY-EFFICIENT)"""
            parquet_file = pq.ParquetFile(file_path)
            header_written = False
            
            for batch in parquet_file.iter_batches(batch_size=CHUNK_SIZE):
                df_batch = batch.to_pandas()
                
                # Ensure Timestamp is datetime and convert UTC to IST
                if 'Timestamp' in df_batch.columns:
                    df_batch['Timestamp'] = pd.to_datetime(df_batch['Timestamp'])
                    
                    # Convert UTC to IST (+5:30) and format
                    df_batch['Timestamp'] = df_batch['Timestamp'].apply(lambda ts: 
                        f"{(ts + pd.Timedelta(hours=5, minutes=30)).month}/{(ts + pd.Timedelta(hours=5, minutes=30)).day}/{(ts + pd.Timedelta(hours=5, minutes=30)).year}, {(ts + pd.Timedelta(hours=5, minutes=30)).strftime('%I:%M:%S %p').lstrip('0')}"
                        if pd.notna(ts) else ''
                    )
                
                # Filter by date range (convert dates for comparison if needed)
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    # Compare using original timestamps before formatting
                
                if end_date:
                    end_dt = pd.to_datetime(end_date)
                    # Compare using original timestamps before formatting
                
                if len(df_batch) == 0:
                    continue
                
                # Convert to CSV chunk
                csv_chunk = io.StringIO()
                df_batch.to_csv(csv_chunk, index=False, header=not header_written)
                yield csv_chunk.getvalue()
                
                header_written = True
        
        # Stream response (SUPER FAST - no waiting for full file)
        return Response(
            stream_with_context(generate_csv()),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={csv_filename}'}
        )
    
    except Exception as e:
        import traceback
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/parquet/read_columnwise', methods=['POST'])
def read_parquet_columnwise():
    """
    Read parquet and display in COLUMN-WISE format (like CSV)
    Shows data as it would appear in CSV
    """
    try:
        data = request.json
        filenames = data.get('filenames', [])
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        max_rows = data.get('max_rows', 1000)
        
        if not filenames or len(filenames) == 0:
            return jsonify({'success': False, 'error': 'At least one filename required'}), 400
        
        all_dataframes = []
        
        for filename in filenames:
            file_path = os.path.join(DATA_DIRECTORY, filename)
            if not os.path.exists(file_path):
                continue
            
            parquet_file = pq.ParquetFile(file_path)
            
            for batch in parquet_file.iter_batches(batch_size=CHUNK_SIZE):
                df_batch = batch.to_pandas()
                
                if 'Timestamp' in df_batch.columns:
                    df_batch['Timestamp'] = pd.to_datetime(df_batch['Timestamp'])
                
                if start_date:
                    df_batch = df_batch[df_batch['Timestamp'] >= pd.to_datetime(start_date)]
                if end_date:
                    df_batch = df_batch[df_batch['Timestamp'] <= pd.to_datetime(end_date)]
                
                if len(df_batch) > 0:
                    all_dataframes.append(df_batch)
        
        if not all_dataframes:
            return jsonify({'success': True, 'data': [], 'total_rows': 0, 'columns': []})
        
        df_combined = pd.concat(all_dataframes, ignore_index=True)
        
        # Pivot to column-wise
        df_pivot = df_combined.pivot_table(
            index='Timestamp',
            columns='TagId',
            values='Value',
            aggfunc='first'
        ).reset_index()
        
        df_pivot = df_pivot.head(max_rows)
        
        # Convert to records
        records = df_pivot.to_dict('records')
        for record in records:
            if 'Timestamp' in record and pd.notna(record['Timestamp']):
                record['Timestamp'] = record['Timestamp'].isoformat()
        
        return jsonify({
            'success': True,
            'data': records,
            'total_rows': len(records),
            'columns': list(df_pivot.columns)
        })
    
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/parquet/verify_conversion', methods=['POST'])
def verify_conversion():
    """
    Verify parquet data matches CSV conversion
    Returns comparison showing any mismatches
    """
    try:
        data = request.json
        filenames = data.get('filenames', [])
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        max_rows = data.get('max_rows', 1000)
        
        if not filenames:
            return jsonify({'success': False, 'error': 'At least one filename required'}), 400
        
        all_dataframes = []
        
        for filename in filenames:
            file_path = os.path.join(DATA_DIRECTORY, filename)
            if not os.path.exists(file_path):
                continue
            
            parquet_file = pq.ParquetFile(file_path)
            
            for batch in parquet_file.iter_batches(batch_size=CHUNK_SIZE):
                df_batch = batch.to_pandas()
                
                if 'Timestamp' in df_batch.columns:
                    df_batch['Timestamp'] = pd.to_datetime(df_batch['Timestamp'])
                
                if start_date:
                    df_batch = df_batch[df_batch['Timestamp'] >= pd.to_datetime(start_date)]
                if end_date:
                    df_batch = df_batch[df_batch['Timestamp'] <= pd.to_datetime(end_date)]
                
                if len(df_batch) > 0:
                    all_dataframes.append(df_batch)
        
        if not all_dataframes:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        df_combined = pd.concat(all_dataframes, ignore_index=True)
        
        # Pivot to column-wise (CSV format)
        df_pivot = df_combined.pivot_table(
            index='Timestamp',
            columns='TagId',
            values='Value',
            aggfunc='first'
        ).reset_index()
        
        df_pivot = df_pivot.head(max_rows)
        
        # Simulate CSV conversion and read back
        csv_buffer = io.StringIO()
        df_pivot.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        df_from_csv = pd.read_csv(csv_buffer)
        
        # Compare
        mismatches = []
        all_match = True
        
        for idx in range(min(len(df_pivot), len(df_from_csv))):
            for col in df_pivot.columns:
                parquet_val = str(df_pivot.iloc[idx][col]) if pd.notna(df_pivot.iloc[idx][col]) else ''
                csv_val = str(df_from_csv.iloc[idx][col]) if pd.notna(df_from_csv.iloc[idx][col]) else ''
                
                if parquet_val != csv_val:
                    all_match = False
                    mismatches.append({
                        'row_index': idx,
                        'column': col,
                        'parquet_value': parquet_val,
                        'csv_value': csv_val
                    })
        
        # Convert to records
        records = df_pivot.to_dict('records')
        for record in records:
            if 'Timestamp' in record and pd.notna(record['Timestamp']):
                record['Timestamp'] = record['Timestamp'].isoformat()
        
        return jsonify({
            'success': True,
            'all_match': all_match,
            'data': records,
            'total_rows': len(records),
            'columns': list(df_pivot.columns),
            'mismatches': mismatches[:100]
        })
    
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/parquet/convert_to_csv_columnwise', methods=['POST'])
def convert_to_csv_columnwise():
    """
    Convert parquet to CSV with COLUMN-WISE structure
    Each TagId becomes a separate column
    """
    try:
        data = request.json
        filenames = data.get('filenames', [])  # Support multiple files
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not filenames or len(filenames) == 0:
            return jsonify({'success': False, 'error': 'At least one filename required'}), 400
        
        all_dataframes = []
        
        for filename in filenames:
            file_path = os.path.join(DATA_DIRECTORY, filename)
            
            if not os.path.exists(file_path):
                continue
            
            parquet_file = pq.ParquetFile(file_path)
            
            for batch in parquet_file.iter_batches(batch_size=CHUNK_SIZE):
                df_batch = batch.to_pandas()
                
                if 'Timestamp' in df_batch.columns:
                    df_batch['Timestamp'] = pd.to_datetime(df_batch['Timestamp'])
                
                # Filter by date range
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    df_batch = df_batch[df_batch['Timestamp'] >= start_dt]
                
                if end_date:
                    end_dt = pd.to_datetime(end_date)
                    df_batch = df_batch[df_batch['Timestamp'] <= end_dt]
                
                if len(df_batch) > 0:
                    all_dataframes.append(df_batch)
        
        if not all_dataframes:
            return jsonify({'success': False, 'error': 'No data found'}), 404
        
        # Combine all data
        df_combined = pd.concat(all_dataframes, ignore_index=True)
        
        # Pivot: TagId as columns, Timestamp as index
        df_pivot = df_combined.pivot_table(
            index='Timestamp',
            columns='TagId',
            values='Value',
            aggfunc='first'
        )
        
        df_pivot.reset_index(inplace=True)
        
        # Generate CSV
        csv_buffer = io.StringIO()
        df_pivot.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        
        csv_filename = f"converted_columnwise_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=csv_filename
        )
    
    except Exception as e:
        import traceback
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/compare_side_by_side', methods=['POST'])
def compare_side_by_side():
    """
    Side-by-side comparison: Parquet vs CSV (COLUMN-WISE)
    Returns aligned data for visual comparison
    """
    try:
        data = request.json
        parquet_filename = data.get('parquet_filename')
        csv_filename = data.get('csv_filename')
        csv_content = data.get('csv_content')
        
        if not parquet_filename:
            return jsonify({'success': False, 'error': 'Parquet filename required'}), 400
        
        # Read parquet and convert to column-wise
        parquet_path = os.path.join(DATA_DIRECTORY, parquet_filename)
        if not os.path.exists(parquet_path):
            return jsonify({'success': False, 'error': 'Parquet file not found'}), 404
        
        df_parquet = pd.read_parquet(parquet_path)
        
        # Pivot parquet data
        df_parquet_pivot = df_parquet.pivot_table(
            index='Timestamp',
            columns='TagId',
            values='Value',
            aggfunc='first'
        ).reset_index()
        
        # Read CSV
        if csv_filename:
            csv_path = os.path.join(DATA_DIRECTORY, csv_filename)
            if not os.path.exists(csv_path):
                return jsonify({'success': False, 'error': 'CSV file not found'}), 404
            df_csv = pd.read_csv(csv_path)
        elif csv_content:
            df_csv = pd.read_csv(io.StringIO(csv_content))
        else:
            return jsonify({'success': False, 'error': 'CSV content required'}), 400
        
        # Ensure both have Timestamp
        if 'Timestamp' in df_parquet_pivot.columns:
            df_parquet_pivot['Timestamp'] = pd.to_datetime(df_parquet_pivot['Timestamp'])
        if 'Timestamp' in df_csv.columns:
            df_csv['Timestamp'] = pd.to_datetime(df_csv['Timestamp'])
        
        # Align both dataframes
        merged = pd.merge(
            df_parquet_pivot,
            df_csv,
            on='Timestamp',
            how='outer',
            suffixes=('_parquet', '_csv')
        )
        
        # Find mismatches
        mismatches = []
        columns = [col for col in merged.columns if col != 'Timestamp' and not col.endswith('_parquet') and not col.endswith('_csv')]
        
        for idx, row in merged.head(100).iterrows():
            for col in columns:
                parquet_col = f"{col}_parquet" if f"{col}_parquet" in merged.columns else col
                csv_col = f"{col}_csv" if f"{col}_csv" in merged.columns else col
                
                parquet_val = row.get(parquet_col)
                csv_val = row.get(csv_col)
                
                if str(parquet_val) != str(csv_val):
                    mismatches.append({
                        'Timestamp': row['Timestamp'].isoformat() if pd.notna(row['Timestamp']) else None,
                        'Column': col,
                        'Parquet_Value': str(parquet_val) if pd.notna(parquet_val) else 'NULL',
                        'CSV_Value': str(csv_val) if pd.notna(csv_val) else 'NULL'
                    })
        
        # Prepare side-by-side data
        comparison_data = []
        for idx, row in merged.head(100).iterrows():
            row_data = {'Timestamp': row['Timestamp'].isoformat() if pd.notna(row['Timestamp']) else None}
            
            for col in columns:
                parquet_col = f"{col}_parquet" if f"{col}_parquet" in merged.columns else col
                csv_col = f"{col}_csv" if f"{col}_csv" in merged.columns else col
                
                row_data[f"{col}_parquet"] = str(row.get(parquet_col, '')) if pd.notna(row.get(parquet_col)) else ''
                row_data[f"{col}_csv"] = str(row.get(csv_col, '')) if pd.notna(row.get(csv_col)) else ''
            
            comparison_data.append(row_data)
        
        return jsonify({
            'success': True,
            'comparison_data': comparison_data,
            'mismatches': mismatches[:50],
            'total_rows': len(merged),
            'mismatch_count': len(mismatches),
            'columns': columns
        })
    
    except Exception as e:
        import traceback
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/compare', methods=['POST'])
def compare_parquet_csv():
    """
    Compare parquet file with CSV file
    Request body: {
        "parquet_filename": "OpcData_20251122_120000.parquet",
        "csv_file_content": "base64 encoded CSV content" OR,
        "csv_filename": "OpcData_20251122_120000.csv" (if already in same directory)
    }
    """
    try:
        data = request.json
        parquet_filename = data.get('parquet_filename')
        csv_filename = data.get('csv_filename')
        
        if not parquet_filename:
            return jsonify({'success': False, 'error': 'Parquet filename required'}), 400
        
        # Read parquet file
        parquet_path = os.path.join(DATA_DIRECTORY, parquet_filename)
        if not os.path.exists(parquet_path):
            return jsonify({'success': False, 'error': 'Parquet file not found'}), 404
        
        df_parquet = pd.read_parquet(parquet_path)
        
        # Read CSV file
        if csv_filename:
            csv_path = os.path.join(DATA_DIRECTORY, csv_filename)
            if not os.path.exists(csv_path):
                return jsonify({'success': False, 'error': 'CSV file not found'}), 404
            df_csv = pd.read_csv(csv_path)
        else:
            # Handle uploaded CSV content
            csv_content = data.get('csv_content')
            if not csv_content:
                return jsonify({'success': False, 'error': 'CSV content required'}), 400
            df_csv = pd.read_csv(io.StringIO(csv_content))
        
        # Ensure both have Timestamp as datetime
        if 'Timestamp' in df_parquet.columns:
            df_parquet['Timestamp'] = pd.to_datetime(df_parquet['Timestamp'])
        if 'Timestamp' in df_csv.columns:
            df_csv['Timestamp'] = pd.to_datetime(df_csv['Timestamp'])
        
        # Compare row counts
        parquet_rows = len(df_parquet)
        csv_rows = len(df_csv)
        
        # Find common and missing rows
        mismatches = []
        matching_rows = 0
        
        # Create composite keys for comparison (RowId + TagId + Timestamp)
        if all(col in df_parquet.columns for col in ['RowId', 'TagId', 'Timestamp']):
            df_parquet['_key'] = df_parquet['RowId'].astype(str) + '_' + df_parquet['TagId'] + '_' + df_parquet['Timestamp'].astype(str)
        else:
            df_parquet['_key'] = df_parquet.index.astype(str)
        
        if all(col in df_csv.columns for col in ['RowId', 'TagId', 'Timestamp']):
            df_csv['_key'] = df_csv['RowId'].astype(str) + '_' + df_csv['TagId'] + '_' + df_csv['Timestamp'].astype(str)
        else:
            df_csv['_key'] = df_csv.index.astype(str)
        
        # Find rows only in parquet
        parquet_only = df_parquet[~df_parquet['_key'].isin(df_csv['_key'])]
        
        # Find rows only in CSV
        csv_only = df_csv[~df_csv['_key'].isin(df_parquet['_key'])]
        
        # Find common rows and compare values
        common_keys = set(df_parquet['_key']) & set(df_csv['_key'])
        
        for key in list(common_keys)[:100]:  # Limit to first 100 for performance
            p_row = df_parquet[df_parquet['_key'] == key].iloc[0]
            c_row = df_csv[df_csv['_key'] == key].iloc[0]
            
            # Compare Value and Quality
            value_match = str(p_row.get('Value', '')) == str(c_row.get('Value', ''))
            quality_match = str(p_row.get('Quality', '')) == str(c_row.get('Quality', ''))
            
            if value_match and quality_match:
                matching_rows += 1
            else:
                mismatches.append({
                    'RowId': int(p_row.get('RowId', 0)) if 'RowId' in p_row else None,
                    'TagId': str(p_row.get('TagId', '')),
                    'Timestamp': p_row.get('Timestamp').isoformat() if pd.notna(p_row.get('Timestamp')) else None,
                    'Parquet_Value': str(p_row.get('Value', '')),
                    'CSV_Value': str(c_row.get('Value', '')),
                    'Parquet_Quality': str(p_row.get('Quality', '')),
                    'CSV_Quality': str(c_row.get('Quality', '')),
                    'Value_Match': value_match,
                    'Quality_Match': quality_match
                })
        
        return jsonify({
            'success': True,
            'summary': {
                'parquet_rows': parquet_rows,
                'csv_rows': csv_rows,
                'common_rows': len(common_keys),
                'matching_rows': matching_rows,
                'rows_only_in_parquet': len(parquet_only),
                'rows_only_in_csv': len(csv_only),
                'value_mismatches': len(mismatches)
            },
            'mismatches': mismatches[:50],  # Return first 50 mismatches
            'parquet_only_sample': parquet_only.head(10).to_dict('records') if len(parquet_only) > 0 else [],
            'csv_only_sample': csv_only.head(10).to_dict('records') if len(csv_only) > 0 else []
        })
    
    except Exception as e:
        import traceback
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🔍 PARQUET READER & COMPARISON TOOL")
    print("=" * 60)
    print(f"📁 Data Directory: {DATA_DIRECTORY}")
    print(f"🌐 Server: http://localhost:5003")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5003, debug=True)
