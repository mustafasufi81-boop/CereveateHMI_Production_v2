/**
 * DATA PROCESSOR MODULE
 * Handles all data transformations and calculations
 */

class DataProcessor {
    
    /**
     * Normalize values to 0-100 scale
     * @param {Array} values - Array of numeric values
     * @returns {Object} - {normalized: Array, min: Number, max: Number, range: Number}
     */
    static normalizeToScale(values) {
        const filtered = values.filter(v => v !== null && v !== undefined && !isNaN(v));
        if (filtered.length === 0) return { normalized: values, min: 0, max: 0, range: 0 };
        
        const min = Math.min(...filtered);
        const max = Math.max(...filtered);
        const range = max - min;
        
        if (range === 0) {
            // All same value = 50%
            const normalized = values.map(v => v !== null && v !== undefined && !isNaN(v) ? 50 : null);
            return { normalized, min, max, range: 0 };
        }
        
        const normalized = values.map(v => {
            if (v === null || v === undefined || isNaN(v)) return null;
            return ((v - min) / range) * 100;
        });
        
        return { normalized, min, max, range };
    }
    
    /**
     * Denormalize values back to original scale
     * @param {Array} normalizedValues - Normalized values (0-100)
     * @param {Number} min - Original minimum
     * @param {Number} max - Original maximum
     * @returns {Array} - Original scale values
     */
    static denormalizeFromScale(normalizedValues, min, max) {
        const range = max - min;
        
        if (range === 0) {
            return normalizedValues.map(() => min);
        }
        
        return normalizedValues.map(v => {
            if (v === null || v === undefined || isNaN(v)) return null;
            return (v / 100) * range + min;
        });
    }
    
    /**
     * Resample data to reduce points based on time interval
     * @param {Array} data - Original data array
     * @param {Number} intervalSeconds - Sampling interval in seconds (0 = no sampling)
     * @returns {Array} - Resampled data
     */
    /**
     * Resample data to reduce number of points
     * IMPROVED VERSION with multiple strategies
     * 
     * @param {Array} data - Array of data points with Timestamp
     * @param {Number} intervalSeconds - Sampling interval in seconds (0 = no sampling)
     * @param {String} method - Sampling method: 'first', 'last', 'average', 'min', 'max', 'median'
     * @returns {Array} - Resampled data
     * 
     * HOW IT WORKS:
     * 1. Groups data into time buckets (e.g., every 60 seconds)
     * 2. For each bucket, selects ONE representative point based on method:
     *    - 'first': Takes first point in bucket (DEFAULT - fastest)
     *    - 'last': Takes last point in bucket
     *    - 'average': Calculates average of all values in bucket (best for smooth trends)
     *    - 'min': Takes minimum value in bucket (good for worst-case analysis)
     *    - 'max': Takes maximum value in bucket (good for peak detection)
     *    - 'median': Takes median value in bucket (good for noisy data)
     * 
     * EXAMPLE with 30-second sampling:
     * Original data (every 1 second):
     *   10:00:00 → 100
     *   10:00:01 → 102
     *   10:00:29 → 105
     *   10:00:30 → 110
     *   10:00:31 → 108
     *   10:00:59 → 115
     *   10:01:00 → 120
     * 
     * Result (30-second buckets):
     *   Bucket 1 (10:00:00-10:00:29): 
     *     - first=100, last=105, avg=102.3, min=100, max=105, median=102
     *   Bucket 2 (10:00:30-10:00:59):
     *     - first=110, last=115, avg=111, min=108, max=115, median=110
     *   Bucket 3 (10:01:00-...):
     *     - first=120, last=120, avg=120, min=120, max=120, median=120
     */
    static resampleData(data, intervalSeconds, method = 'first') {
        if (!intervalSeconds || intervalSeconds <= 0 || data.length === 0) {
            return data;
        }
        
        const intervalMs = intervalSeconds * 1000;
        
        // Method 1: FIRST POINT (Current method - fastest, simple)
        if (method === 'first') {
            const result = [];
            let lastTimestamp = null;
            
            data.forEach(point => {
                const currentTime = new Date(point.Timestamp).getTime();
                
                if (lastTimestamp === null || currentTime - lastTimestamp >= intervalMs) {
                    result.push(point);
                    lastTimestamp = currentTime;
                }
            });
            
            console.log(`📉 Resampled (First-Point): ${data.length} → ${result.length} points (${intervalSeconds}s interval)`);
            return result;
        }
        
        // Method 2-6: BUCKET-BASED SAMPLING (groups data into time windows)
        // Step 1: Group data into time buckets
        const buckets = new Map(); // Map<bucketKey, Array<dataPoint>>
        
        data.forEach(point => {
            const timestamp = new Date(point.Timestamp).getTime();
            const bucketKey = Math.floor(timestamp / intervalMs);
            
            if (!buckets.has(bucketKey)) {
                buckets.set(bucketKey, []);
            }
            buckets.get(bucketKey).push(point);
        });
        
        // Step 2: Select one point from each bucket based on method
        const result = [];
        const sortedBucketKeys = Array.from(buckets.keys()).sort((a, b) => a - b);
        
        sortedBucketKeys.forEach(bucketKey => {
            const bucketPoints = buckets.get(bucketKey);
            let selectedPoint;
            
            switch (method) {
                case 'last':
                    // Take LAST point in bucket
                    selectedPoint = bucketPoints[bucketPoints.length - 1];
                    break;
                    
                case 'average':
                case 'mean':
                    // Calculate AVERAGE of all values in bucket
                    selectedPoint = this._averageBucket(bucketPoints);
                    break;
                    
                case 'min':
                    // Take point with MINIMUM value in bucket
                    selectedPoint = this._minMaxBucket(bucketPoints, 'min');
                    break;
                    
                case 'max':
                    // Take point with MAXIMUM value in bucket
                    selectedPoint = this._minMaxBucket(bucketPoints, 'max');
                    break;
                    
                case 'median':
                    // Take MEDIAN value in bucket
                    selectedPoint = this._medianBucket(bucketPoints);
                    break;
                    
                default:
                    // Default to first
                    selectedPoint = bucketPoints[0];
            }
            
            result.push(selectedPoint);
        });
        
        console.log(`📉 Resampled (${method}): ${data.length} → ${result.length} points (${intervalSeconds}s, ${buckets.size} buckets)`);
        return result;
    }
    
    /**
     * Helper: Calculate average of all values in a bucket
     */
    static _averageBucket(bucketPoints) {
        if (bucketPoints.length === 1) return bucketPoints[0];
        
        const avgPoint = { ...bucketPoints[0] }; // Copy first point structure
        
        // Get all tag names (columns except Timestamp)
        const tags = Object.keys(bucketPoints[0]).filter(key => key !== 'Timestamp');
        
        // Calculate average for each tag
        tags.forEach(tag => {
            const values = bucketPoints.map(p => p[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
            if (values.length > 0) {
                avgPoint[tag] = values.reduce((sum, v) => sum + v, 0) / values.length;
            }
        });
        
        // Use middle timestamp of bucket
        const timestamps = bucketPoints.map(p => new Date(p.Timestamp).getTime());
        const avgTimestamp = timestamps.reduce((sum, t) => sum + t, 0) / timestamps.length;
        avgPoint.Timestamp = new Date(avgTimestamp).toISOString();
        
        return avgPoint;
    }
    
    /**
     * Helper: Find point with min/max value in bucket
     */
    static _minMaxBucket(bucketPoints, type) {
        if (bucketPoints.length === 1) return bucketPoints[0];
        
        // Find which tag has the most variation to determine min/max
        const tags = Object.keys(bucketPoints[0]).filter(key => key !== 'Timestamp');
        let selectedPoint = bucketPoints[0];
        
        // Use first numeric tag to determine min/max
        const primaryTag = tags.find(tag => {
            const val = bucketPoints[0][tag];
            return val !== null && val !== undefined && !isNaN(val);
        });
        
        if (primaryTag) {
            if (type === 'min') {
                selectedPoint = bucketPoints.reduce((minPoint, point) => {
                    return (point[primaryTag] < minPoint[primaryTag]) ? point : minPoint;
                });
            } else {
                selectedPoint = bucketPoints.reduce((maxPoint, point) => {
                    return (point[primaryTag] > maxPoint[primaryTag]) ? point : maxPoint;
                });
            }
        }
        
        return selectedPoint;
    }
    
    /**
     * Helper: Calculate median of bucket
     */
    static _medianBucket(bucketPoints) {
        if (bucketPoints.length === 1) return bucketPoints[0];
        
        const medianPoint = { ...bucketPoints[0] };
        const tags = Object.keys(bucketPoints[0]).filter(key => key !== 'Timestamp');
        
        tags.forEach(tag => {
            const values = bucketPoints.map(p => p[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
            if (values.length > 0) {
                values.sort((a, b) => a - b);
                const mid = Math.floor(values.length / 2);
                medianPoint[tag] = values.length % 2 === 0 
                    ? (values[mid - 1] + values[mid]) / 2 
                    : values[mid];
            }
        });
        
        // Use middle timestamp
        const timestamps = bucketPoints.map(p => new Date(p.Timestamp).getTime());
        timestamps.sort((a, b) => a - b);
        const mid = Math.floor(timestamps.length / 2);
        medianPoint.Timestamp = new Date(timestamps[mid]).toISOString();
        
        return medianPoint;
    }
    
    /**
     * Calculate statistics for a dataset via Python API
     * @param {Array} values - Array of numeric values
     * @returns {Object} - Statistics object
     */
    static async calculateStats(values) {
        try {
            // Convert values array to data format for API
            const data = values.map(v => ({ value: v }));
            
            const response = await fetch(`${window.location.origin}/api/v1/analytics/statistics`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    data: data,
                    tags: ['value']
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                const stats = result.value;
                
                if (stats) {
                    // Convert Python API format to expected format
                    return {
                        mean: stats.mean,
                        stdDev: stats.std_dev,
                        min: stats.min,
                        max: stats.max,
                        median: stats.median,
                        q1: stats.q1,
                        q3: stats.q3,
                        iqr: stats.q3 - stats.q1,
                        lowerBound: stats.mean - 3 * stats.std_dev,
                        upperBound: stats.mean + 3 * stats.std_dev,
                        count: stats.count
                    };
                }
            }
        } catch (error) {
            console.error('Statistics API Error:', error);
            throw error;
        }
        
        return null;
    }
    
    /**
     * Detect anomalies using 3-sigma method
     * @param {Array} data - Data array
     * @param {String} tag - Tag name
     * @returns {Object} - Anomalies and stats
     */
    static detectAnomalies(data, tag) {
        const values = data.map(d => parseFloat(d[tag])).filter(v => v !== null && v !== undefined && !isNaN(v));
        const stats = this.calculateStats(values);
        if (!stats) return { anomalies: [], stats: null };
        
        const anomalies = data.map((d, idx) => {
            const value = d[tag];
            if (value === null || value === undefined || isNaN(value)) return null;
            
            const isAnomaly = value < stats.lowerBound || value > stats.upperBound;
            return isAnomaly ? { index: idx, timestamp: d.Timestamp, value, tag } : null;
        }).filter(a => a !== null);
        
        return { anomalies, stats };
    }
    
    /**
     * Find peak moments (best/worst) for a tag
     * @param {Array} data - Data array
     * @param {String} targetTag - Tag to analyze
     * @param {String} type - 'best' or 'worst'
     * @returns {Object} - Peak information
     */
    static findPeakMoment(data, targetTag, type) {
        if (!data || data.length === 0) return null;
        
        let peakValue = type === 'best' ? -Infinity : Infinity;
        let peakTimestamp, peakIndex;
        
        data.forEach((row, idx) => {
            const val = row[targetTag];
            if (val !== null && val !== undefined && !isNaN(val)) {
                if (type === 'best' && val > peakValue) {
                    peakValue = val;
                    peakTimestamp = row.Timestamp;
                    peakIndex = idx;
                } else if (type === 'worst' && val < peakValue) {
                    peakValue = val;
                    peakTimestamp = row.Timestamp;
                    peakIndex = idx;
                }
            }
        });
        
        if (peakIndex === undefined) return null;
        
        return {
            value: peakValue,
            timestamp: peakTimestamp,
            index: peakIndex
        };
    }
    
    /**
     * Get window data around a specific timestamp
     * @param {Array} data - Data array
     * @param {String} timestamp - Center timestamp
     * @param {Number} windowMinutes - Window size in minutes (default: 10)
     * @returns {Array} - Filtered data
     */
    static getWindowData(data, timestamp, windowMinutes = 10) {
        const centerTime = new Date(timestamp);
        const windowMs = windowMinutes * 60 * 1000;
        const startTime = new Date(centerTime.getTime() - windowMs);
        const endTime = new Date(centerTime.getTime() + windowMs);
        
        return data.filter(row => {
            const rowTime = new Date(row.Timestamp);
            return rowTime >= startTime && rowTime <= endTime;
        });
    }
    
    /**
     * Calculate parameter statistics at a specific index
     * @param {Array} data - Data array
     * @param {Array} tags - Tags to analyze
     * @param {Number} targetIndex - Index of peak moment
     * @param {String} excludeTag - Tag to exclude (usually the target tag)
     * @returns {Object} - Tag statistics
     */
    static calculateParameterStatsAtMoment(data, tags, targetIndex, excludeTag = null) {
        const windowData = this.getWindowData(data, data[targetIndex].Timestamp);
        const tagStats = {};
        
        tags.forEach(tag => {
            if (tag === excludeTag) return;
            
            const windowValues = windowData
                .map(row => parseFloat(row[tag]))
                .filter(v => v !== null && v !== undefined && !isNaN(v));
            
            if (windowValues.length === 0) {
                tagStats[tag] = null;
                return;
            }
            
            const peakMomentValue = data[targetIndex][tag];
            const stats = this.calculateStats(windowValues);
            
            tagStats[tag] = {
                atPeak: peakMomentValue,
                ...stats
            };
        });
        
        return tagStats;
    }
}

// Export for use in main script (both Node.js and browser)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DataProcessor;
} else if (typeof window !== 'undefined') {
    window.DataProcessor = DataProcessor;
}
