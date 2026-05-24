"""
Parquet Data Generator - Main Application
Modular Flask UI with background services - DYNAMIC TAG DISCOVERY
Port: 5004
"""
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import json
import os
from pathlib import Path

from simulation_engine_dynamic import DynamicSimulationEngine
from file_transfer_service import FileTransferService
from backup_service import BackupService

app = Flask(__name__)
CORS(app)

# Load configuration
config_path = Path(__file__).parent / 'config.json'
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Initialize services with dynamic tag discovery
simulation_engine = DynamicSimulationEngine(config)
transfer_service = FileTransferService(config)
backup_service = BackupService(config)

# Auto-start services ONLY if AutoStartOnLaunch is enabled
if config.get('SystemMode', {}).get('AutoStartOnLaunch', False):
    print("[AUTO-START] Background mode activated - starting all enabled services...")
    
    if config['Simulation']['Enabled']:
        result = simulation_engine.start()
        print(f"[AUTO-START] Simulation: {result['message']}")
    
    if config['FileTransfer']['Enabled']:
        result = transfer_service.start()
        print(f"[AUTO-START] Transfer: {result['message']}")
    
    if config['Backup']['Enabled']:
        result = backup_service.start()
        print(f"[AUTO-START] Backup: {result['message']}")
    
    print("[AUTO-START] All services started - running in background mode")
else:
    print("[UI MODE] Services ready - use web UI to start/stop services")


@app.route('/')
def index():
    """Main UI page"""
    return render_template('index.html', config=config)


@app.route('/api/status')
def get_status():
    """Get status of all services"""
    return jsonify({
        'simulation': simulation_engine.get_stats(),
        'transfer': transfer_service.get_status(),
        'backup': backup_service.get_status(),
        'config': {
            'simulation_enabled': config['Simulation']['Enabled'],
            'transfer_enabled': config['FileTransfer']['Enabled'],
            'backup_enabled': config['Backup']['Enabled'],
            'simulation_interval': config['Simulation']['IntervalSeconds'],
            'transfer_interval': config['FileTransfer']['TransferIntervalSeconds'],
            'total_tags': len(config['Tags']),
            'auto_start': config.get('SystemMode', {}).get('AutoStartOnLaunch', False),
            'background_mode': config.get('SystemMode', {}).get('BackgroundMode', False)
        }
    })


@app.route('/api/system/mode', methods=['POST'])
def set_system_mode():
    """Set system mode - UI control or background auto-run"""
    data = request.json
    auto_start = data.get('auto_start', False)
    background_mode = data.get('background_mode', False)
    
    # Update config
    if 'SystemMode' not in config:
        config['SystemMode'] = {}
    
    config['SystemMode']['AutoStartOnLaunch'] = auto_start
    config['SystemMode']['BackgroundMode'] = background_mode
    
    # Save to file
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    mode_description = "Background Auto-Run" if auto_start else "UI-Controlled"
    return jsonify({
        'success': True, 
        'message': f'System mode set to: {mode_description}',
        'auto_start': auto_start,
        'background_mode': background_mode
    })


@app.route('/api/simulation/start', methods=['POST'])
def start_simulation():
    """Start simulation"""
    result = simulation_engine.start()
    return jsonify(result)


@app.route('/api/simulation/stop', methods=['POST'])
def stop_simulation():
    """Stop simulation"""
    result = simulation_engine.stop()
    return jsonify(result)


@app.route('/api/transfer/start', methods=['POST'])
def start_transfer():
    """Start file transfer"""
    result = transfer_service.start()
    return jsonify(result)


@app.route('/api/transfer/stop', methods=['POST'])
def stop_transfer():
    """Stop file transfer"""
    result = transfer_service.stop()
    return jsonify(result)


@app.route('/api/backup/start', methods=['POST'])
def start_backup():
    """Start backup service"""
    result = backup_service.start()
    return jsonify(result)


@app.route('/api/backup/stop', methods=['POST'])
def stop_backup():
    """Stop backup service"""
    result = backup_service.stop()
    return jsonify(result)


@app.route('/api/config/service', methods=['POST'])
def update_service_config():
    """Enable/disable services and save to config"""
    data = request.json
    service = data.get('service')  # 'simulation', 'transfer', 'backup'
    enabled = data.get('enabled', True)
    
    if service == 'simulation':
        config['Simulation']['Enabled'] = enabled
    elif service == 'transfer':
        config['FileTransfer']['Enabled'] = enabled
    elif service == 'backup':
        config['Backup']['Enabled'] = enabled
    else:
        return jsonify({'success': False, 'message': 'Invalid service name'})
    
    # Save config
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    status = "enabled" if enabled else "disabled"
    return jsonify({'success': True, 'message': f'{service.capitalize()} service {status}'})


@app.route('/api/config/backup', methods=['POST'])
def update_backup_config():
    """Update backup directory"""
    data = request.json
    backup_dir = data.get('backup_directory')
    
    if not backup_dir:
        return jsonify({'success': False, 'message': 'Backup directory required'})
    
    config['Paths']['BackupDirectory'] = backup_dir
    config['Backup']['Enabled'] = True
    
    # Save config
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    return jsonify({'success': True, 'message': 'Backup directory updated'})


if __name__ == '__main__':
    auto_start = config.get('SystemMode', {}).get('AutoStartOnLaunch', False)
    background_mode = config.get('SystemMode', {}).get('BackgroundMode', False)
    mode = "BACKGROUND AUTO-RUN" if auto_start else "UI-CONTROLLED"
    
    print("=" * 60)
    print("Parquet Data Generator - Turbine Plant Simulation")
    print("=" * 60)
    print(f"System Mode: {mode}")
    print(f"Simulation Output: {config['Paths']['SimulationOutputDirectory']}")
    print(f"Main Data Directory: {config['Paths']['MainDataDirectory']}")
    print(f"Backup Directory: {config['Paths']['BackupDirectory'] or 'Not configured'}")
    print(f"Total Tags: {len(config['Tags'])}")
    
    if auto_start:
        print(f"Services: Running in background (UI controls disabled)")
    else:
        print(f"Services: Controlled via Web UI")
    
    print("=" * 60)
    print("Starting server on http://localhost:5004")
    print("=" * 60)
    
    app.run(host='127.0.0.1', port=5004, debug=False, threaded=True)
