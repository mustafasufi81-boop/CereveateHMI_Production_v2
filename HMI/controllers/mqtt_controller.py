"""
MQTT Controller
API endpoints for MQTT topic and tag information
"""

from flask import Blueprint, jsonify
from container import container
import logging

mqtt_bp = Blueprint('mqtt', __name__, url_prefix='/api/mqtt')
logger = logging.getLogger(__name__)


@mqtt_bp.route('/topics', methods=['GET'])
def get_mqtt_topics():
    """
    Get all active MQTT topics with their PLC mappings
    
    Returns:
        JSON array of topics with plc_name and subscription status
    """
    try:
        if not container.topic_tag_mapper:
            return jsonify({'error': 'MQTT service not initialized'}), 503
        
        # Get active topics from mapper
        topics = container.topic_tag_mapper.get_active_topics()
        
        # Add subscription status if MQTT client is available
        if container.mqtt_client:
            for topic in topics:
                topic['subscribed'] = container.mqtt_client.is_topic_subscribed(topic['topic_name'])
                topic['connected'] = container.mqtt_client.is_connected
        else:
            for topic in topics:
                topic['subscribed'] = False
                topic['connected'] = False
        
        return jsonify({
            'topics': topics,
            'total': len(topics)
        })
        
    except Exception as e:
        logger.error(f"Error getting MQTT topics: {e}")
        return jsonify({'error': str(e)}), 500


@mqtt_bp.route('/topics/<path:topic_name>/tags', methods=['GET'])
def get_tags_for_topic(topic_name):
    """
    Get all tags associated with a specific MQTT topic
    
    Args:
        topic_name: MQTT topic name (e.g., 'plant/gateway/data')
        
    Returns:
        JSON array of tags for the topic's PLC
    """
    try:
        if not container.topic_tag_mapper:
            return jsonify({'error': 'MQTT service not initialized'}), 503
        
        # Get tags for this topic
        tags = container.topic_tag_mapper.get_tags_for_topic(topic_name)
        plc_name = container.topic_tag_mapper.get_plc_for_topic(topic_name)
        
        if not tags:
            return jsonify({
                'topic': topic_name,
                'plc_name': plc_name,
                'tags': [],
                'message': 'No tags found for this topic'
            }), 404
        
        return jsonify({
            'topic': topic_name,
            'plc_name': plc_name,
            'tags': tags,
            'total': len(tags)
        })
        
    except Exception as e:
        logger.error(f"Error getting tags for topic {topic_name}: {e}")
        return jsonify({'error': str(e)}), 500


@mqtt_bp.route('/plcs', methods=['GET'])
def get_plcs():
    """
    Get all PLCs with their MQTT topics and tag counts
    
    Returns:
        JSON array of PLCs with associated topics and tag counts
    """
    try:
        if not container.topic_tag_mapper:
            return jsonify({'error': 'MQTT service not initialized'}), 503
        
        summary = container.topic_tag_mapper.get_summary()
        
        # Build PLC information
        plc_info = []
        for plc_name in summary['plcs']:
            topic = container.topic_tag_mapper.get_topic_for_plc(plc_name)
            tags = container.topic_tag_mapper.get_tags_for_plc(plc_name)
            
            plc_info.append({
                'plc_name': plc_name,
                'topic': topic,
                'tag_count': len(tags),
                'tags': tags[:10]  # Sample of first 10 tags
            })
        
        return jsonify({
            'plcs': plc_info,
            'total': len(plc_info),
            'summary': summary
        })
        
    except Exception as e:
        logger.error(f"Error getting PLCs: {e}")
        return jsonify({'error': str(e)}), 500


@mqtt_bp.route('/plcs/<plc_name>/tags', methods=['GET'])
def get_tags_for_plc(plc_name):
    """
    Get all tags for a specific PLC
    
    Args:
        plc_name: PLC name (server_progid)
        
    Returns:
        JSON array of tags for the PLC
    """
    try:
        if not container.topic_tag_mapper:
            return jsonify({'error': 'MQTT service not initialized'}), 503
        
        tags = container.topic_tag_mapper.get_tags_for_plc(plc_name)
        topic = container.topic_tag_mapper.get_topic_for_plc(plc_name)
        
        if not tags:
            return jsonify({
                'plc_name': plc_name,
                'topic': topic,
                'tags': [],
                'message': 'No tags found for this PLC'
            }), 404
        
        return jsonify({
            'plc_name': plc_name,
            'topic': topic,
            'tags': tags,
            'total': len(tags)
        })
        
    except Exception as e:
        logger.error(f"Error getting tags for PLC {plc_name}: {e}")
        return jsonify({'error': str(e)}), 500


@mqtt_bp.route('/status', methods=['GET'])
def get_mqtt_status():
    """
    Get MQTT client connection status and statistics
    
    Returns:
        JSON with connection status and subscribed topics
    """
    try:
        status = {
            'service_initialized': container.mqtt_client is not None,
            'connected': False,
            'subscribed_topics': [],
            'mapper_loaded': False,
            'topic_count': 0,
            'plc_count': 0,
            'tag_count': 0
        }
        
        if container.mqtt_client:
            status['connected'] = container.mqtt_client.is_connected
            status['subscribed_topics'] = container.mqtt_client.get_subscribed_topics()
        
        if container.topic_tag_mapper:
            summary = container.topic_tag_mapper.get_summary()
            status['mapper_loaded'] = True
            status['topic_count'] = summary['total_topics']
            status['plc_count'] = summary['total_plcs']
            status['tag_count'] = summary['total_tags']
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting MQTT status: {e}")
        return jsonify({'error': str(e)}), 500
