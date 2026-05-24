from flask import Blueprint, jsonify

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """API root - React frontend is served separately"""
    return jsonify({
        'message': 'HMI API Backend',
        'version': '2.0',
        'frontend': 'http://localhost:5173',
        'status': 'ok'
    })

@main_bp.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})
