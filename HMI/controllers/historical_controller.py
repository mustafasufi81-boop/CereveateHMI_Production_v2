from flask import Blueprint, jsonify, request, g
from container import container
from datetime import datetime, timedelta
import logging
from utils.decorators import token_required, get_user_allowed_tag_filter

logger = logging.getLogger(__name__)
historical_bp = Blueprint('historical', __name__, url_prefix='/api')


def get_tag_info(tag_id):
    """Get plant/area info for a tag to check permissions"""
    try:
        with container.historical_service.connection.cursor() as cursor:
            cursor.execute("""
                SELECT plant, area FROM historian_meta.tag_master WHERE tag_id = %s
            """, (tag_id,))
            row = cursor.fetchone()
            return row if row else {'plant': None, 'area': None}
    except:
        return {'plant': None, 'area': None}

@historical_bp.route('/historical/<tag_id>')
@token_required
def get_historical(tag_id):
    """
    Get historical trend data from PostgreSQL (RBAC protected)
    """
    try:
        # Check RBAC permission for this tag
        tag_filter = get_user_allowed_tag_filter()
        if tag_filter is not None:
            tag_info = get_tag_info(tag_id)
            if not tag_filter(tag_id, tag_info.get('plant'), tag_info.get('area')):
                return jsonify({'error': 'Access denied to this tag'}), 403
        # Parse parameters
        start_str = request.args.get('start')
        end_str = request.args.get('end')
        mode = request.args.get('mode', 'raw')
        max_points = int(request.args.get('max_points', 50000))
        
        # Parse timestamps
        if start_str and end_str:
            start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        else:
            # Default: last 1 hour
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
        
        if not container.historical_service.connection:
            return jsonify({'error': 'Database not connected'}), 503
        
        with container.historical_service.connection.cursor() as cursor:
            if mode == 'raw':
                # FAST RAW QUERY: Get exact values, no aggregation
                # Use LIMIT with subquery sampling for large datasets
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND time >= %s
                    AND time <= %s
                """, (tag_id, start_time, end_time))
                
                total_count = cursor.fetchone()['count']
                
                if total_count <= max_points:
                    # Small dataset - return all raw values
                    query = """
                        SELECT time, value_num, quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND time >= %s
                        AND time <= %s
                        ORDER BY time ASC
                    """
                    cursor.execute(query, (tag_id, start_time, end_time))
                else:
                    # Large dataset - sample every Nth row (keep exact values!)
                    sample_every = max(1, total_count // max_points)
                    
                    query = f"""
                        WITH numbered AS (
                            SELECT time, value_num, quality,
                                   ROW_NUMBER() OVER (ORDER BY time ASC) as rn
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = %s
                            AND time >= %s
                            AND time <= %s
                        )
                        SELECT time, value_num, quality
                        FROM numbered
                        WHERE rn % {sample_every} = 1
                        ORDER BY time ASC
                        LIMIT %s
                    """
                    cursor.execute(query, (tag_id, start_time, end_time, max_points))
                
                rows = cursor.fetchall()
                
                # Return exact raw values
                data = [
                    {
                        'timestamp': row['time'].isoformat(),
                        'value': float(row['value_num']) if row['value_num'] is not None else None,
                        'quality': row['quality']
                    }
                    for row in rows
                ]
                
                return jsonify({
                    'tagId': tag_id,
                    'startTime': start_time.isoformat(),
                    'endTime': end_time.isoformat(),
                    'mode': 'raw',
                    'count': len(data),
                    'totalRows': total_count,
                    'data': data
                })
            else:
                return jsonify({'error': 'Invalid mode'}), 400
        
    except Exception as e:
        logger.error(f"❌ Historical query error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@historical_bp.route('/historical/multiple', methods=['POST'])
@token_required
def get_multiple_historical():
    """
    Get historical data for multiple tags (RBAC protected)
    """
    try:
        data = request.json
        
        # Filter tag_ids by RBAC permissions
        tag_filter = get_user_allowed_tag_filter()
        requested_tags = data.get('tagIds', [])
        
        logger.info(f"🔐 RBAC Multiple: requested_tags={requested_tags}, filter={tag_filter is not None}")
        
        if tag_filter is not None:
            allowed_tags = []
            for tag_id in requested_tags:
                tag_info = get_tag_info(tag_id)
                is_allowed = tag_filter(tag_id, tag_info.get('plant'), tag_info.get('area'))
                logger.info(f"🔐 RBAC Check: tag={tag_id}, plant={tag_info.get('plant')}, area={tag_info.get('area')}, allowed={is_allowed}")
                if is_allowed:
                    allowed_tags.append(tag_id)
            tag_ids = allowed_tags
            logger.info(f"🔐 RBAC Result: allowed_tags={allowed_tags}")
        else:
            tag_ids = requested_tags
            logger.info(f"🔐 RBAC: No filter (admin) - all tags allowed")
        
        hours = data.get('hours', 1)
        max_points = data.get('maxPoints', 1000)
        sampling_interval = data.get('samplingInterval')
        
        # Check for explicit time range (ISO strings)
        start_iso = data.get('startTime')
        end_iso = data.get('endTime')
        
        if start_iso and end_iso:
            # Parse ISO timestamps
            start_time = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
        else:
            # Fallback to relative hours
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
        
        results = container.historical_service.get_multiple_trends(
            tag_ids, start_time, end_time, max_points, sampling_interval
        )
        
        return jsonify({
            'startTime': start_time.isoformat(),
            'endTime': end_time.isoformat(),
            'trends': results
        })
        
    except Exception as e:
        logger.error(f"❌ Multiple historical query error: {e}")
        return jsonify({'error': str(e)}), 500


@historical_bp.route('/historian/historical')
def get_historian_historical():
    """
    Get historian data for single tag with INDUSTRIAL-GRADE AGGREGATION (frontend format - NO AUTH for now)
    Query params: tag, start_time, end_time, limit, aggregation (optional)
    
    Aggregation modes (ISA-101 compliant):
    - 'raw': Raw data points (for short time ranges)
    - 'avg': Time-bucketed averages (for longer time ranges)
    - 'auto': Automatically choose based on time span (recommended)
    """
    try:
        tag = request.args.get('tag')
        start_time_str = request.args.get('start_time')
        end_time_str = request.args.get('end_time')
        limit = int(request.args.get('limit', 50000))  # Max cache limit
        aggregation = request.args.get('aggregation', 'auto')
        
        # DEBUG: Log all incoming parameters
        logger.info("=" * 80)
        logger.info("📥 INCOMING REQUEST PARAMETERS:")
        logger.info(f"   tag: {tag}")
        logger.info(f"   start_time: {start_time_str}")
        logger.info(f"   end_time: {end_time_str}")
        logger.info(f"   limit: {limit}")
        logger.info(f"   aggregation: {aggregation}")
        logger.info("=" * 80)
        
        if not tag or not start_time_str or not end_time_str:
            return jsonify({'error': 'Missing required parameters: tag, start_time, end_time'}), 400
        
        # Check if we received DATE ONLY (YYYY-MM-DD) or full timestamp
        is_date_only = len(start_time_str) == 10 and len(end_time_str) == 10
        logger.info(f"🔍 PARSING MODE: is_date_only={is_date_only} (len(start)={len(start_time_str)}, len(end)={len(end_time_str)})")
        
        if is_date_only:
            # DATE ONLY mode: Query by date, ignore time
            logger.info(f"📅 DATE ONLY MODE ACTIVATED")
            logger.info(f"   Start Date: {start_time_str}")
            logger.info(f"   End Date: {end_time_str}")
            start_date = start_time_str
            end_date = end_time_str
            
            # Calculate time span (assume full days)
            from datetime import datetime as dt
            start_dt = dt.strptime(start_date, '%Y-%m-%d')
            end_dt = dt.strptime(end_date, '%Y-%m-%d')
            time_span_minutes = (end_dt - start_dt).total_seconds() / 60
        else:
            # Full timestamp mode
            logger.info(f"⏰ FULL TIMESTAMP MODE ACTIVATED")
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            logger.info(f"   Start Timestamp: {start_time}")
            logger.info(f"   End Timestamp: {end_time}")
            
            # Calculate time span in minutes
            time_span_minutes = (end_time - start_time).total_seconds() / 60
        
        # INDUSTRY STANDARD: Choose aggregation based on time span
        # This follows PI System, Wonderware, and Ignition historian practices
        if aggregation == 'auto':
            if time_span_minutes <= 5:  # <= 5 minutes
                aggregation = 'raw'
                bucket_interval = None
                date_trunc_unit = None
            elif time_span_minutes <= 60:  # 5 min - 1 hour
                aggregation = 'avg'
                bucket_interval = '15 seconds'
                date_trunc_unit = 'second'
            elif time_span_minutes <= 480:  # 1-8 hours
                aggregation = 'avg'
                bucket_interval = '1 minute'
                date_trunc_unit = 'minute'
            elif time_span_minutes <= 2880:  # 8 hours - 2 days
                aggregation = 'avg'
                bucket_interval = '5 minutes'
                date_trunc_unit = 'minute'
            elif time_span_minutes <= 10080:  # 2 days - 1 week
                aggregation = 'avg'
                bucket_interval = '15 minutes'
                date_trunc_unit = 'minute'
            elif time_span_minutes <= 43200:  # 1-30 days
                aggregation = 'avg'
                bucket_interval = '30 minutes'
                date_trunc_unit = 'minute'
            else:  # > 30 days
                aggregation = 'avg'
                bucket_interval = '1 hour'
                date_trunc_unit = 'hour'
        else:
            # Manual aggregation specified
            bucket_interval = '1 minute' if aggregation == 'avg' else None
            date_trunc_unit = 'minute' if aggregation == 'avg' else None
        
        logger.info(f"📊 AGGREGATION DECISION:")
        logger.info(f"   Time Span: {time_span_minutes:.1f} minutes ({time_span_minutes/60:.1f} hours, {time_span_minutes/1440:.1f} days)")
        logger.info(f"   Aggregation: {aggregation}")
        logger.info(f"   Bucket Interval: {bucket_interval}")
        logger.info(f"   Date Trunc Unit: {date_trunc_unit}")
        logger.info(f"   Limit: {limit}")
        
        if not container.historical_service.connection:
            logger.error("❌ DATABASE NOT CONNECTED!")
            return jsonify({'error': 'Database not connected'}), 503
        
        with container.historical_service.connection.cursor() as cursor:
            if is_date_only:
                # DATE ONLY MODE: Query by date, ignore time completely
                if aggregation == 'raw':
                    sql_query = """
                        SELECT time,
                            COALESCE(value_num,
                                CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                     THEN value_text::numeric ELSE NULL END
                            ) AS value_num
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND DATE(time) >= %s
                        AND DATE(time) <= %s
                        ORDER BY time ASC
                        LIMIT %s
                    """
                    query_params = (tag, start_date, end_date, limit)
                    logger.info(f"🗄️  EXECUTING SQL (DATE ONLY - RAW):")
                    logger.info(f"   Query: {sql_query.strip()}")
                    logger.info(f"   Params: tag={tag}, start_date={start_date}, end_date={end_date}, limit={limit}")
                    cursor.execute(sql_query, query_params)
                else:
                    # Aggregation with DATE ONLY
                    # Support both seconds and minutes bucket intervals
                    if bucket_interval and ('second' in bucket_interval or 'minute' in bucket_interval):
                        # Parse bucket interval (e.g., "15 seconds" -> 15, "5 minutes" -> 300)
                        parts = bucket_interval.split()
                        interval_num = int(parts[0])
                        interval_unit = parts[1]
                        
                        if 'second' in interval_unit:
                            bucket_seconds = interval_num
                        else:  # minutes
                            bucket_seconds = interval_num * 60
                        
                        sql_query = """
                            SELECT 
                                to_timestamp(floor(extract(epoch from time) / %s) * %s) AS bucket_time,
                                AVG(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_avg,
                                MIN(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_min,
                                MAX(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_max,
                                COUNT(*) as point_count
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = %s
                            AND DATE(time) >= %s
                            AND DATE(time) <= %s
                            GROUP BY bucket_time
                            ORDER BY bucket_time ASC
                            LIMIT %s
                        """
                        query_params = (bucket_seconds, bucket_seconds, tag, start_date, end_date, limit)
                        logger.info(f"🗄️  EXECUTING SQL (DATE ONLY - AGGREGATED - SECONDS):")
                        logger.info(f"   Bucket Seconds: {bucket_seconds}")
                        logger.info(f"   Params: tag={tag}, start_date={start_date}, end_date={end_date}, limit={limit}")
                        cursor.execute(sql_query, query_params)
                    else:
                        sql_query = """
                            SELECT 
                                date_trunc(%s, time) AS bucket_time,
                                AVG(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_avg,
                                MIN(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_min,
                                MAX(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_max,
                                COUNT(*) as point_count
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = %s
                            AND DATE(time) >= %s
                            AND DATE(time) <= %s
                            GROUP BY bucket_time
                            ORDER BY bucket_time ASC
                            LIMIT %s
                        """
                        query_params = (date_trunc_unit, tag, start_date, end_date, limit)
                        logger.info(f"🗄️  EXECUTING SQL (DATE ONLY - AGGREGATED - DATE_TRUNC):")
                        logger.info(f"   Date Trunc Unit: {date_trunc_unit}")
                        logger.info(f"   Params: tag={tag}, start_date={start_date}, end_date={end_date}, limit={limit}")
                        cursor.execute(sql_query, query_params)
            else:
                # FULL TIMESTAMP MODE (existing logic)
                logger.info(f"⏰ FULL TIMESTAMP MODE QUERY PATH")
                if aggregation == 'raw':
                    # RAW MODE: Get exact data points (for short time ranges)
                    sql_query = """
                        SELECT time,
                            COALESCE(value_num,
                                CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                     THEN value_text::numeric ELSE NULL END
                            ) AS value_num
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND time >= %s
                        AND time <= %s
                        ORDER BY time ASC
                        LIMIT %s
                    """
                    query_params = (tag, start_time, end_time, limit)
                    logger.info(f"🗄️  EXECUTING SQL (TIMESTAMP - RAW):")
                    logger.info(f"   Query: {sql_query.strip()}")
                    logger.info(f"   Params: tag={tag}, start_time={start_time}, end_time={end_time}, limit={limit}")
                    cursor.execute(sql_query, query_params)
                else:
                    # AGGREGATION MODE: Use standard PostgreSQL date_trunc() for compatibility
                    # Falls back to date_trunc instead of TimescaleDB's time_bucket()
                    # For sub-hour intervals, use epoch-based bucketing
                    
                    # Support both seconds and minutes bucket intervals
                    if bucket_interval and ('second' in bucket_interval or 'minute' in bucket_interval):
                        # Parse bucket interval (e.g., "15 seconds" -> 15, "5 minutes" -> 300)
                        parts = bucket_interval.split()
                        interval_num = int(parts[0])
                        interval_unit = parts[1]
                        
                        if 'second' in interval_unit:
                            bucket_seconds = interval_num
                        else:  # minutes
                            bucket_seconds = interval_num * 60
                        
                        sql_query = """
                            SELECT 
                                to_timestamp(floor(extract(epoch from time) / %s) * %s) AS bucket_time,
                                AVG(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_avg,
                                MIN(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_min,
                                MAX(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_max,
                                COUNT(*) as point_count
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = %s
                            AND time >= %s
                            AND time <= %s
                            GROUP BY bucket_time
                            ORDER BY bucket_time ASC
                            LIMIT %s
                        """
                        query_params = (bucket_seconds, bucket_seconds, tag, start_time, end_time, limit)
                        logger.info(f"🗄️  EXECUTING SQL (TIMESTAMP - AGGREGATED - SECONDS):")
                        logger.info(f"   Bucket Seconds: {bucket_seconds}")
                        logger.info(f"   Params: tag={tag}, start_time={start_time}, end_time={end_time}, limit={limit}")
                        cursor.execute(sql_query, query_params)
                    else:
                        # For hourly aggregation, use date_trunc
                        sql_query = """
                            SELECT 
                                date_trunc(%s, time) AS bucket_time,
                                AVG(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_avg,
                                MIN(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_min,
                                MAX(COALESCE(value_num,
                                    CASE WHEN value_text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                                         THEN value_text::numeric ELSE NULL END)) as value_max,
                                COUNT(*) as point_count
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = %s
                            AND time >= %s
                            AND time <= %s
                            GROUP BY bucket_time
                            ORDER BY bucket_time ASC
                            LIMIT %s
                        """
                        query_params = (date_trunc_unit, tag, start_time, end_time, limit)
                        logger.info(f"🗄️  EXECUTING SQL (TIMESTAMP - AGGREGATED - DATE_TRUNC):")
                        logger.info(f"   Date Trunc Unit: {date_trunc_unit}")
                        logger.info(f"   Params: tag={tag}, start_time={start_time}, end_time={end_time}, limit={limit}")
                        cursor.execute(sql_query, query_params)
            
            rows = cursor.fetchall()
            
            # DIAGNOSTIC: Log query results
            logger.info("=" * 80)
            logger.info(f"📊 QUERY RESULTS:")
            logger.info(f"   Tag: {tag}")
            logger.info(f"   Aggregation: {aggregation}")
            logger.info(f"   Bucket: {bucket_interval}")
            logger.info(f"   Requested Range: {start_time_str} → {end_time_str}")
            logger.info(f"   Time Span: {time_span_minutes:.0f} minutes")
            logger.info(f"   Rows Returned: {len(rows)}")
            
            if len(rows) > 0:
                first_ts = rows[0].get('time') or rows[0].get('bucket_time')
                last_ts = rows[-1].get('time') or rows[-1].get('bucket_time')
                logger.info(f"   First Record Timestamp: {first_ts}")
                logger.info(f"   Last Record Timestamp: {last_ts}")
                
                # Log sample of first 3 and last 3 data points
                logger.info(f"   Sample Data (first 3):")
                for i, row in enumerate(rows[:3]):
                    ts = row.get('time') or row.get('bucket_time')
                    val = row.get('value_num') or row.get('value_avg')
                    logger.info(f"      [{i+1}] {ts} = {val}")
                
                if len(rows) > 6:
                    logger.info(f"   Sample Data (last 3):")
                    for i, row in enumerate(rows[-3:]):
                        ts = row.get('time') or row.get('bucket_time')
                        val = row.get('value_num') or row.get('value_avg')
                        logger.info(f"      [{len(rows)-3+i+1}] {ts} = {val}")
            else:
                logger.warning(f"⚠️  NO RECORDS FOUND!")
                logger.warning(f"   Tag: {tag}")
                logger.warning(f"   Requested Range: {start_time_str} → {end_time_str}")
                
                # Check if ANY data exists for this tag
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        MIN(time) as earliest,
                        MAX(time) as latest
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                """, (tag,))
                info = cursor.fetchone()
                logger.warning(f"   Tag '{tag}' Total Records: {info['total']}")
                logger.warning(f"   Available Range: {info['earliest']} to {info['latest']}")
                
                # Check if data exists in the requested date range
                if is_date_only:
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND DATE(time) >= %s
                        AND DATE(time) <= %s
                    """, (tag, start_date, end_date))
                    range_count = cursor.fetchone()
                    logger.warning(f"   Records in requested date range: {range_count['count']}")
            
            # Transform data based on aggregation mode
            logger.info(f"🔄 TRANSFORMING DATA FOR RESPONSE:")
            logger.info(f"   Aggregation Mode: {aggregation}")
            logger.info(f"   Row Count: {len(rows)}")
            
            if aggregation == 'raw':
                logger.info(f"   Using 'time' column for raw data timestamps")
                data = [
                    {
                        'timestamp': row['time'].isoformat(),
                        'value': float(row['value_num']) if row['value_num'] is not None else None
                    }
                    for row in rows
                ]
            else:
                # For aggregated data, use average value (industry standard)
                logger.info(f"   Using 'bucket_time' column for aggregated data timestamps")
                data = [
                    {
                        'timestamp': row['bucket_time'].isoformat(),
                        'value': float(row['value_avg']) if row['value_avg'] is not None else None,
                        'min': float(row['value_min']) if row['value_min'] is not None else None,
                        'max': float(row['value_max']) if row['value_max'] is not None else None,
                        'count': row['point_count']
                    }
                    for row in rows
                ]
            
            logger.info("=" * 80)
            logger.info(f"✅ RESPONSE READY:")
            logger.info(f"   Tag: {tag}")
            logger.info(f"   Data Points: {len(data)}")
            logger.info(f"   Aggregation: {aggregation}")
            logger.info(f"   Bucket Interval: {bucket_interval}")
            logger.info(f"   Time Span: {time_span_minutes:.1f} minutes")
            
            if len(data) > 0:
                logger.info(f"   First Data Point: {data[0]['timestamp']} = {data[0]['value']}")
                logger.info(f"   Last Data Point: {data[-1]['timestamp']} = {data[-1]['value']}")
            
            logger.info(f"✅ Sending response to frontend with {len(data)} data points")
            logger.info("=" * 80)
            
            return jsonify({
                'tag': tag,
                'data': data,
                'count': len(data),
                'aggregation': aggregation,
                'bucket_interval': bucket_interval,
                'time_span_minutes': time_span_minutes
            })
        
    except Exception as e:
        logger.error(f"❌ Historian query error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@historical_bp.route('/historian/tags')
def get_historian_tags():
    """Get list of available historian tags (NO AUTH for now)"""
    try:
        if not container.historical_service.connection:
            return jsonify({'error': 'Database not connected'}), 503
        
        with container.historical_service.connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT tag_id
                FROM historian_raw.historian_timeseries
                ORDER BY tag_id
                LIMIT 1000
            """)
            
            rows = cursor.fetchall()
            tags = [row['tag_id'] for row in rows]
            
            return jsonify({
                'tags': tags,
                'count': len(tags)
            })
        
    except Exception as e:
        logger.error(f"❌ Get tags error: {e}")
        return jsonify({'error': str(e)}), 500


@historical_bp.route('/statistics/<tag_id>')
@token_required
def get_statistics(tag_id):
    """Get statistical summary for a tag (RBAC protected)"""
    try:
        # Check RBAC permission for this tag
        tag_filter = get_user_allowed_tag_filter()
        if tag_filter is not None:
            tag_info = get_tag_info(tag_id)
            if not tag_filter(tag_id, tag_info.get('plant'), tag_info.get('area')):
                return jsonify({'error': 'Access denied to this tag'}), 403
        hours = int(request.args.get('hours', 24))
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        stats = container.historical_service.get_tag_statistics(tag_id, start_time, end_time)
        
        return jsonify({
            'tagId': tag_id,
            'timeRange': f'{hours}h',
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"❌ Statistics query error: {e}")
        return jsonify({'error': str(e)}), 500
