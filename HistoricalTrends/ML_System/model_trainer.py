"""
Model Trainer - Trains all models and logs performance separately
NO hardcoding - uses discovered parameters
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from storage_manager import SmartStorageManager
from model_registry import ModelRegistry
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Trains all registered models
    Uses discovered parameters automatically
    Logs each model's performance separately
    """
    
    def __init__(self, config):
        self.config = config
        self.storage = SmartStorageManager()
        self.registry = ModelRegistry()
        
        self.min_training_days = config['models']['training']['initial_training_days']
        self.validation_split = config['models']['training']['validation_split']
        self.target_column = config['models']['training'].get('target_column', 'Load')
        
        logger.info(f"Model Trainer initialized (target: {self.target_column})")
    
    def has_sufficient_data(self):
        """Check if enough data collected for training"""
        try:
            files = self.storage.list_files('01_RawData')
            
            if len(files) < self.min_training_days:
                logger.info(f"Need {self.min_training_days} days, have {len(files)} files")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking data: {e}")
            return False
    
    def load_training_data(self):
        """Load all available training data"""
        try:
            files = self.storage.list_files('01_RawData')
            
            if not files:
                logger.warning("No training data found")
                return None
            
            # Load all files
            dfs = []
            for f in files:
                try:
                    df = self.storage.load('01_RawData', f.stem)
                    dfs.append(df)
                except Exception as e:
                    logger.debug(f"Skipping file {f}: {e}")
            
            if not dfs:
                return None
            
            # Combine
            combined = pd.concat(dfs, ignore_index=True)
            logger.info(f"Loaded {len(combined)} training samples")
            
            return combined
            
        except Exception as e:
            logger.error(f"Error loading training data: {e}")
            return None
    
    def get_important_features(self, top_n=50):
        """Get most important features from discovery"""
        try:
            rankings = self.storage.load('02_DiscoveredParameters', 
                                        'parameter_importance_scores')
            
            # Sort by importance
            rankings = rankings.sort_values('importance_score', ascending=False)
            
            # Take top N
            top_features = rankings.head(top_n)['parameter'].tolist()
            
            logger.info(f"Using top {len(top_features)} features for training")
            return top_features
            
        except FileNotFoundError:
            logger.warning("No parameter rankings found, using all columns")
            return None
        except Exception as e:
            logger.error(f"Error loading feature rankings: {e}")
            return None
    
    def prepare_features(self, df, target_col=None):
        """
        Prepare features and target for training
        Uses discovered important parameters
        """
        if target_col is None:
            target_col = self.target_column
        
        if target_col not in df.columns:
            logger.error(f"Target column {target_col} not found")
            return None, None
        
        # Get important features
        important_features = self.get_important_features()
        
        if important_features:
            # Use discovered features
            feature_cols = [c for c in important_features if c in df.columns and c != target_col]
        else:
            # Use all numeric columns except target
            feature_cols = [c for c in df.columns 
                          if c not in ['timestamp', target_col] 
                          and pd.api.types.is_numeric_dtype(df[c])]
        
        if not feature_cols:
            logger.error("No valid features found")
            return None, None
        
        # Prepare X and y
        X = df[feature_cols].fillna(0)  # Simple imputation
        y = df[target_col].fillna(0)
        
        logger.info(f"Prepared {len(feature_cols)} features for training")
        return X, y
    
    def train_all_models(self):
        """
        Train all registered models
        Each model logs its own performance
        """
        logger.info("Starting model training...")
        
        # Load data
        df = self.load_training_data()
        
        if df is None or len(df) < 1000:
            logger.warning("Insufficient training data")
            return False
        
        # Prepare features
        X, y = self.prepare_features(df)
        
        if X is None:
            logger.error("Feature preparation failed")
            return False
        
        # Train/validation split
        X_train, X_val, y_train, y_val = train_test_split(
            X, y,
            test_size=self.validation_split,
            random_state=42
        )
        
        logger.info(f"Training set: {len(X_train)} samples")
        logger.info(f"Validation set: {len(X_val)} samples")
        
        # Train all models
        results = self.registry.train_all(X_train, y_train, X_val, y_val)
        
        # Log summary
        logger.info("Training complete:")
        for model_name, status in results.items():
            logger.info(f"  {model_name}: {status}")
        
        # Save models
        for model_name, model in self.registry.models.items():
            if model.trained:
                try:
                    model.save_model()
                except Exception as e:
                    logger.error(f"Failed to save {model_name}: {e}")
        
        logger.info("All models trained and saved")
        return True


if __name__ == '__main__':
    # Test model trainer
    logging.basicConfig(level=logging.INFO)
    
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    trainer = ModelTrainer(config)
    
    print("Testing model trainer...")
    
    if trainer.has_sufficient_data():
        print("✓ Sufficient data available")
        success = trainer.train_all_models()
        
        if success:
            print("✓ Training successful")
        else:
            print("✗ Training failed")
    else:
        print("✗ Not enough data yet")
