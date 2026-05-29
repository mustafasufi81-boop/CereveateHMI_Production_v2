"""
Data Collector - Async data collection from OPC/sensors
Runs continuously without blocking system
"""

import asyncio
import pandas as pd
from datetime import datetime
import logging
from storage_manager import SmartStorageManager
import yaml

logger = logging.getLogger(__name__)


class DataCollector:
    """
    Collects data from all available sources
    NO hardcoded parameters - discovers everything
    """
    
    def __init__(self, config):
        self.config = config
        self.storage = SmartStorageManager()
        
        # Get data source from config
        self.data_source = config['data_collection']['parameter_source']
        self.auto_discover = config['data_collection']['auto_discover_parameters']
        
        self.discovered_tags = []
        
        logger.info(f"Data Collector initialized (source: {self.data_source})")
    
    def collect_from_opc(self):
        """Collect data from OPC server"""
        try:
            # Import OPC service from main app
            import sys
            sys.path.append('..')
            from Services.OpcDaService import OpcDaService
            
            opc = OpcDaService()
            
            if not opc.is_connected:
                logger.warning("OPC not connected, attempting connection...")
                # OPC connection will be handled by main app
                return None
            
            # Get all available tags if auto-discover
            if self.auto_discover and not self.discovered_tags:
                self.discovered_tags = opc.get_all_tags()
                logger.info(f"Discovered {len(self.discovered_tags)} OPC tags")
            
            # Read all discovered tags
            data = {}
            data['timestamp'] = datetime.now()
            
            for tag in self.discovered_tags:
                try:
                    value = opc.read_tag(tag)
                    data[tag] = value
                except Exception as e:
                    logger.debug(f"Failed to read {tag}: {e}")
                    data[tag] = None
            
            return pd.DataFrame([data])
            
        except Exception as e:
            logger.error(f"OPC collection failed: {e}")
            return None
    
    def collect_from_csv(self):
        """Collect data from CSV files (for testing)"""
        try:
            # Look for latest CSV in Logs directory
            from pathlib import Path
            
            logs_dir = Path('../Logs')
            if not logs_dir.exists():
                logger.warning("Logs directory not found")
                return None
            
            # Get most recent OPC data file
            csv_files = sorted(logs_dir.glob('OpcData_*.csv'))
            if not csv_files:
                logger.warning("No OPC data CSV files found")
                return None
            
            latest_file = csv_files[-1]
            
            # Read last N rows (recent data only)
            df = pd.read_csv(latest_file)
            
            # Take last 100 rows
            recent_data = df.tail(100)
            
            # Auto-discover tags from columns
            if self.auto_discover and not self.discovered_tags:
                self.discovered_tags = [c for c in recent_data.columns if c != 'Timestamp']
                logger.info(f"Discovered {len(self.discovered_tags)} tags from CSV")
            
            return recent_data
            
        except Exception as e:
            logger.error(f"CSV collection failed: {e}")
            return None
    
    def collect_from_database(self):
        """Collect data from database"""
        # Placeholder for database collection
        logger.warning("Database collection not implemented yet")
        return None
    
    def collect_data(self):
        """
        Collect data from configured source
        Returns DataFrame with all parameters
        """
        if self.data_source == 'opc_server':
            return self.collect_from_opc()
        elif self.data_source == 'csv_files':
            return self.collect_from_csv()
        elif self.data_source == 'database':
            return self.collect_from_database()
        else:
            logger.error(f"Unknown data source: {self.data_source}")
            return None
    
    def collect_and_store(self):
        """
        Main collection method
        Collects data and stores in appropriate format
        """
        logger.debug("Collecting data...")
        
        # Collect data
        data = self.collect_data()
        
        if data is None or len(data) == 0:
            logger.warning("No data collected")
            return False
        
        try:
            # Store raw data
            filename = f"turbine_data_YYYYMMDD"
            self.storage.save(data, '01_RawData', filename)
            
            logger.info(f"Collected and stored {len(data)} data points")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store data: {e}")
            return False
    
    def get_discovered_parameters(self):
        """Return list of discovered parameters"""
        return self.discovered_tags


if __name__ == '__main__':
    # Test data collector
    logging.basicConfig(level=logging.INFO)
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    collector = DataCollector(config)
    
    print("Testing data collection...")
    success = collector.collect_and_store()
    
    if success:
        print(f"✓ Data collection successful")
        print(f"✓ Discovered {len(collector.get_discovered_parameters())} parameters")
    else:
        print("✗ Data collection failed")
