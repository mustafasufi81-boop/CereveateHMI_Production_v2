import json
import os

class ConfigReader:
    """Reads logging configuration to get parquet file paths"""
    
    def __init__(self):
        self.config_path = None
        self.config = None
        self._find_config()
    
    def _find_config(self):
        """Find logging-config.json in parent directories"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Search up to 3 levels
        for _ in range(3):
            config_file = os.path.join(current_dir, 'logging-config.json')
            if os.path.exists(config_file):
                self.config_path = config_file
                self._load_config()
                return
            
            # Check in bin/Release/net8.0/win-x86
            bin_config = os.path.join(current_dir, 'bin', 'Release', 'net8.0', 'win-x86', 'logging-config.json')
            if os.path.exists(bin_config):
                self.config_path = bin_config
                self._load_config()
                return
            
            current_dir = os.path.dirname(current_dir)
        
        # Default fallback
        self.config = {
            "LoggingPaths": {
                "DataLogDirectory": "D:\\Logs\\Data\\OPC",
                "BackupDirectory": "D:\\Backup\\OpcLogs"
            }
        }
    
    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {
                "LoggingPaths": {
                    "DataLogDirectory": "D:\\Logs\\Data\\OPC",
                    "BackupDirectory": "D:\\Backup\\OpcLogs"
                }
            }
    
    def get_data_directory(self):
        """Get the parquet data directory path"""
        return self.config.get('LoggingPaths', {}).get('DataLogDirectory', 'D:\\Logs\\Data\\OPC')
    
    def get_backup_directory(self):
        """Get the backup directory path"""
        return self.config.get('LoggingPaths', {}).get('BackupDirectory', 'D:\\Backup\\OpcLogs')
