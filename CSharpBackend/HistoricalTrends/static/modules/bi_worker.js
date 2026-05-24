/**
 * Web Worker for BI Analytics Heavy Calculations
 * Prevents UI blocking during large data processing
 */

self.onmessage = function(e) {
    const { type, data, tags } = e.data;
    
    try {
        let result;
        
        switch(type) {
            case 'correlation':
                result = calculateCorrelationMatrix(data, tags);
                break;
            case 'statistics':
                result = calculateStatistics(data, tags);
                break;
            case 'aggregation':
                result = aggregateData(data, tags, e.data.buckets);
                break;
            case 'sampling':
                result = sampleData(data, e.data.maxPoints);
                break;
            default:
                throw new Error('Unknown operation type');
        }
        
        self.postMessage({ success: true, result });
    } catch (error) {
        self.postMessage({ success: false, error: error.message });
    }
};

/**
 * Calculate correlation matrix
 */
function calculateCorrelationMatrix(data, tags) {
    const matrix = [];
    
    tags.forEach(tag1 => {
        const row = [];
        tags.forEach(tag2 => {
            const values1 = data.filter(d => d[tag1] != null && d[tag2] != null).map(d => d[tag1]);
            const values2 = data.filter(d => d[tag1] != null && d[tag2] != null).map(d => d[tag2]);
            
            if (values1.length === 0 || values2.length === 0) {
                row.push(0);
                return;
            }
            
            const mean1 = values1.reduce((a, b) => a + b, 0) / values1.length;
            const mean2 = values2.reduce((a, b) => a + b, 0) / values2.length;
            
            let numerator = 0;
            let sum1 = 0;
            let sum2 = 0;
            
            for (let i = 0; i < values1.length; i++) {
                const diff1 = values1[i] - mean1;
                const diff2 = values2[i] - mean2;
                numerator += diff1 * diff2;
                sum1 += diff1 * diff1;
                sum2 += diff2 * diff2;
            }
            
            const denominator = Math.sqrt(sum1 * sum2);
            const correlation = denominator === 0 ? 0 : numerator / denominator;
            row.push(correlation);
        });
        matrix.push(row);
    });
    
    return matrix;
}

/**
 * Calculate comprehensive statistics
 */
function calculateStatistics(data, tags) {
    const stats = {};
    
    tags.forEach(tag => {
        const values = data.filter(d => d[tag] != null && !isNaN(d[tag])).map(d => d[tag]);
        
        if (values.length === 0) {
            stats[tag] = null;
            return;
        }
        
        const sorted = [...values].sort((a, b) => a - b);
        const mean = values.reduce((a, b) => a + b, 0) / values.length;
        const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
        const stdDev = Math.sqrt(variance);
        
        const q1Index = Math.floor(sorted.length * 0.25);
        const q3Index = Math.floor(sorted.length * 0.75);
        const medianIndex = Math.floor(sorted.length * 0.5);
        
        stats[tag] = {
            count: values.length,
            mean: mean,
            median: sorted[medianIndex],
            min: sorted[0],
            max: sorted[sorted.length - 1],
            range: sorted[sorted.length - 1] - sorted[0],
            stdDev: stdDev,
            variance: variance,
            q1: sorted[q1Index],
            q3: sorted[q3Index],
            iqr: sorted[q3Index] - sorted[q1Index],
            cv: mean !== 0 ? (stdDev / Math.abs(mean)) * 100 : 0, // Coefficient of Variation
            stability: stdDev / (sorted[sorted.length - 1] - sorted[0] + 1), // Stability index
        };
    });
    
    return stats;
}

/**
 * Aggregate data into buckets
 */
function aggregateData(data, tags, numBuckets) {
    const bucketSize = Math.ceil(data.length / numBuckets);
    const buckets = [];
    
    for (let i = 0; i < data.length; i += bucketSize) {
        const bucket = data.slice(i, i + bucketSize);
        buckets.push(bucket);
    }
    
    const aggregated = buckets.map((bucket, index) => {
        const result = { bucketId: index };
        
        tags.forEach(tag => {
            const values = bucket.filter(d => d[tag] != null && !isNaN(d[tag])).map(d => d[tag]);
            result[tag] = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : 0;
        });
        
        return result;
    });
    
    return aggregated;
}

/**
 * Sample data for performance
 */
function sampleData(data, maxPoints) {
    if (data.length <= maxPoints) {
        return data;
    }
    
    const step = Math.ceil(data.length / maxPoints);
    return data.filter((_, i) => i % step === 0);
}
