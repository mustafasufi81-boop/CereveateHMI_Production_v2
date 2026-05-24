"""
Simple test script to debug Advanced BI workflow
Runs on port 5001, prints everything to console
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify
from bi_engines.delta_scorer import DeltaScorer
from bi_engines.efficiency_engine import EfficiencyEngine
from bi_engines.availability_engine import AvailabilityEngine
from bi_engines.baseline_engine import BaselineEngine

app = Flask(__name__)

# Initialize engines
delta_scorer = DeltaScorer()
efficiency_engine = EfficiencyEngine()
availability_engine = AvailabilityEngine()
baseline_engine = BaselineEngine()

@app.route('/api/v1/delta/calculate', methods=['POST'])
def calculate_delta():
    print("\n" + "="*80)
    print("🔵 DELTA ENDPOINT CALLED")
    print("="*80)
    
    try:
        data = request.get_json()
        print(f"📥 Received data: {data}")
        
        actual = data.get('actual')
        expected = data.get('expected')
        metadata = data.get('metadata', {})
        timestamp = data.get('timestamp')
        
        print(f"   actual: {actual} (type: {type(actual)})")
        print(f"   expected: {expected} (type: {type(expected)})")
        print(f"   metadata: {metadata}")
        print(f"   timestamp: {timestamp}")
        
        # Type conversion
        actual = float(actual) if actual is not None else 0.0
        expected = float(expected) if expected is not None else 0.0
        
        print(f"✅ After conversion:")
        print(f"   actual: {actual}")
        print(f"   expected: {expected}")
        
        # Call engine
        print(f"🔧 Calling delta_scorer.calculate_weighted_delta...")
        result = delta_scorer.calculate_weighted_delta(actual, expected, metadata, timestamp)
        
        print(f"📤 Result from engine: {result}")
        print(f"   Type: {type(result)}")
        
        if result:
            print(f"   raw_delta: {result.get('raw_delta')}")
            print(f"   weighted_delta: {result.get('weighted_delta')}")
            print(f"   performance_score: {result.get('performance_score')}")
            print(f"   condition: {result.get('condition')}")
        
        print("✅ Returning 200 OK")
        print("="*80 + "\n")
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        print(f"   Type: {type(e)}")
        import traceback
        traceback.print_exc()
        print("="*80 + "\n")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/efficiency/calculate', methods=['POST'])
def calculate_efficiency():
    print("\n" + "="*80)
    print("🟢 EFFICIENCY ENDPOINT CALLED")
    print("="*80)
    
    try:
        data = request.get_json()
        print(f"📥 Received data: {data}")
        
        baseline_value = float(data.get('baseline_value', 0))
        loss_factor = float(data.get('loss_factor', 0))
        
        print(f"   baseline_value: {baseline_value}")
        print(f"   loss_factor: {loss_factor}")
        
        print(f"🔧 Calling efficiency_engine.calculate_adjusted_expected...")
        result = efficiency_engine.calculate_adjusted_expected(baseline_value, loss_factor)
        
        print(f"📤 Result: {result}")
        print("✅ Returning 200 OK")
        print("="*80 + "\n")
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("="*80 + "\n")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/availability/calculate', methods=['POST'])
def calculate_availability():
    print("\n" + "="*80)
    print("🟡 AVAILABILITY ENDPOINT CALLED")
    print("="*80)
    
    try:
        data = request.get_json()
        print(f"📥 Received data: {data}")
        
        total_seconds = float(data.get('total_seconds', 0))
        actual_production = float(data.get('actual_production', 0))
        
        print(f"   total_seconds: {total_seconds}")
        print(f"   actual_production: {actual_production}")
        
        print(f"🔧 Calling availability_engine.calculate_availability_production...")
        result = availability_engine.calculate_availability_production(total_seconds, actual_production)
        
        print(f"📤 Result: {result}")
        print("✅ Returning 200 OK")
        print("="*80 + "\n")
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("="*80 + "\n")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/baseline/calculate', methods=['POST'])
def calculate_baseline():
    print("\n" + "="*80)
    print("🟣 BASELINE ENDPOINT CALLED")
    print("="*80)
    
    try:
        data = request.get_json()
        print(f"📥 Received data (first 200 chars): {str(data)[:200]}")
        
        values = data.get('values', [])
        window_days = data.get('window_days', 30)
        
        print(f"   values count: {len(values)}")
        print(f"   window_days: {window_days}")
        
        print(f"🔧 Calling baseline_engine.calculate_adaptive_baseline...")
        result = baseline_engine.calculate_adaptive_baseline(values, window_days)
        
        print(f"📤 Result: {result}")
        print("✅ Returning 200 OK")
        print("="*80 + "\n")
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("="*80 + "\n")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*80)
    print("🚀 STARTING DEBUG SERVER ON PORT 5001")
    print("="*80)
    print("Endpoints available:")
    print("  - POST /api/v1/delta/calculate")
    print("  - POST /api/v1/efficiency/calculate")
    print("  - POST /api/v1/availability/calculate")
    print("  - POST /api/v1/baseline/calculate")
    print("="*80 + "\n")
    
    app.run(host='127.0.0.1', port=5001, debug=False, threaded=True)
