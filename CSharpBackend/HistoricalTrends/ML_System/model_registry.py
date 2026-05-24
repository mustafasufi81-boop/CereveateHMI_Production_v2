"""
Model Registry - Manages all ML models with zero hardcoding
Each model is self-contained and logs its own performance
"""

import yaml
import logging
import importlib
from datetime import datetime
import pandas as pd
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseModel(ABC):
    """
    Base class for all ML models
    Forces consistent interface - NO hardcoding allowed
    """
    
    def __init__(self, config, storage):
        self.config = config
        self.storage = storage
        self.model_name = self.__class__.__name__
        self.model = None
        self.trained = False
        self.version = 1
        
        logger.info(f"Initialized {self.model_name}")
    
    @abstractmethod
    def train(self, X_train, y_train, X_val, y_val):
        """Train the model - MUST be implemented by each model"""
        pass
    
    @abstractmethod
    def predict(self, X):
        """Make predictions - MUST be implemented by each model"""
        pass
    
    def evaluate(self, X_test, y_test):
        """
        Evaluate model performance
        Returns standardized metrics dict
        """
        predictions = self.predict(X_test)
        
        # Calculate standard metrics
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        import numpy as np
        
        mae = mean_absolute_error(y_test, predictions)
        rmse = np.sqrt(mean_squared_error(y_test, predictions))
        r2 = r2_score(y_test, predictions)
        
        # MAPE (handle division by zero)
        mape = np.mean(np.abs((y_test - predictions) / np.where(y_test != 0, y_test, 1))) * 100
        
        metrics = {
            'MAE': mae,
            'RMSE': rmse,
            'R2': r2,
            'MAPE': mape,
            'samples': len(y_test)
        }
        
        # Log performance automatically
        self.storage.save_model_performance(self.model_name, metrics)
        
        logger.info(f"{self.model_name} Performance: MAE={mae:.4f}, RMSE={rmse:.4f}, R2={r2:.4f}")
        
        return metrics
    
    def save_model(self):
        """Save trained model"""
        import pickle
        from pathlib import Path
        
        if not self.trained:
            logger.warning(f"{self.model_name} not trained, nothing to save")
            return
        
        model_path = Path(self.storage.models_path) / f"{self.model_name}_v{self.version}.pkl"
        
        with open(model_path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'version': self.version,
                'trained_at': datetime.now(),
                'config': self.config
            }, f)
        
        logger.info(f"Saved {self.model_name} to {model_path}")
        return model_path
    
    def load_model(self, version=None):
        """Load trained model"""
        import pickle
        from pathlib import Path
        
        if version is None:
            version = self.version
        
        model_path = Path(self.storage.models_path) / f"{self.model_name}_v{version}.pkl"
        
        if not model_path.exists():
            logger.warning(f"Model file not found: {model_path}")
            return False
        
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
            self.model = data['model']
            self.version = data['version']
            self.trained = True
        
        logger.info(f"Loaded {self.model_name} v{version}")
        return True


class RandomForestModel(BaseModel):
    """Random Forest implementation"""
    
    def train(self, X_train, y_train, X_val, y_val):
        from sklearn.ensemble import RandomForestRegressor
        
        # Get hyperparameters from config or use smart defaults
        n_estimators = self.config.get('n_estimators', 100)
        max_depth = self.config.get('max_depth', None)
        
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(X_train, y_train)
        self.trained = True
        
        # Auto-evaluate on validation set
        self.evaluate(X_val, y_val)
    
    def predict(self, X):
        if not self.trained:
            raise RuntimeError(f"{self.model_name} not trained")
        return self.model.predict(X)


class XGBoostModel(BaseModel):
    """XGBoost implementation"""
    
    def train(self, X_train, y_train, X_val, y_val):
        import xgboost as xgb
        
        # Smart defaults from config
        n_estimators = self.config.get('n_estimators', 100)
        learning_rate = self.config.get('learning_rate', 0.1)
        max_depth = self.config.get('max_depth', 6)
        
        self.model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        self.trained = True
        
        self.evaluate(X_val, y_val)
    
    def predict(self, X):
        if not self.trained:
            raise RuntimeError(f"{self.model_name} not trained")
        return self.model.predict(X)


class LightGBMModel(BaseModel):
    """LightGBM implementation"""
    
    def train(self, X_train, y_train, X_val, y_val):
        import lightgbm as lgb
        
        n_estimators = self.config.get('n_estimators', 100)
        learning_rate = self.config.get('learning_rate', 0.1)
        
        self.model = lgb.LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            random_state=42,
            n_jobs=-1,
            verbose=-1
        )
        
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.log_evaluation(period=0)]
        )
        self.trained = True
        
        self.evaluate(X_val, y_val)
    
    def predict(self, X):
        if not self.trained:
            raise RuntimeError(f"{self.model_name} not trained")
        return self.model.predict(X)


class ProphetModel(BaseModel):
    """Prophet time series model"""
    
    def train(self, X_train, y_train, X_val, y_val):
        from prophet import Prophet
        
        # Prophet needs specific format: ds (datetime), y (value)
        # Assume first column of X is timestamp
        train_df = pd.DataFrame({
            'ds': X_train.iloc[:, 0] if isinstance(X_train, pd.DataFrame) else X_train[:, 0],
            'y': y_train
        })
        
        self.model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False
        )
        
        self.model.fit(train_df)
        self.trained = True
        
        # Evaluate
        val_df = pd.DataFrame({
            'ds': X_val.iloc[:, 0] if isinstance(X_val, pd.DataFrame) else X_val[:, 0]
        })
        
        forecast = self.model.predict(val_df)
        predictions = forecast['yhat'].values
        
        # Manual evaluation since predict is different
        from sklearn.metrics import mean_absolute_error, mean_squared_error
        import numpy as np
        
        mae = mean_absolute_error(y_val, predictions)
        rmse = np.sqrt(mean_squared_error(y_val, predictions))
        
        self.storage.save_model_performance(self.model_name, {
            'MAE': mae,
            'RMSE': rmse,
            'samples': len(y_val)
        })
    
    def predict(self, X):
        if not self.trained:
            raise RuntimeError(f"{self.model_name} not trained")
        
        future_df = pd.DataFrame({
            'ds': X.iloc[:, 0] if isinstance(X, pd.DataFrame) else X[:, 0]
        })
        
        forecast = self.model.predict(future_df)
        return forecast['yhat'].values


class IsolationForestModel(BaseModel):
    """Isolation Forest for anomaly detection"""
    
    def train(self, X_train, y_train=None, X_val=None, y_val=None):
        from sklearn.ensemble import IsolationForest
        
        contamination = self.config.get('contamination', 0.1)
        
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(X_train)
        self.trained = True
        
        logger.info(f"{self.model_name} trained for anomaly detection")
    
    def predict(self, X):
        """Returns -1 for anomalies, 1 for normal"""
        if not self.trained:
            raise RuntimeError(f"{self.model_name} not trained")
        return self.model.predict(X)
    
    def predict_scores(self, X):
        """Returns anomaly scores"""
        if not self.trained:
            raise RuntimeError(f"{self.model_name} not trained")
        return self.model.score_samples(X)


class EnsembleModel(BaseModel):
    """Ensemble of multiple models"""
    
    def __init__(self, config, storage, base_models):
        super().__init__(config, storage)
        self.base_models = base_models  # List of trained models
        
    def train(self, X_train, y_train, X_val, y_val):
        """Ensemble doesn't train - it uses pre-trained models"""
        if not self.base_models:
            raise ValueError("No base models provided for ensemble")
        
        self.trained = True
        self.evaluate(X_val, y_val)
    
    def predict(self, X):
        """Average predictions from all base models"""
        if not self.trained:
            raise RuntimeError(f"{self.model_name} not trained")
        
        predictions = []
        for model in self.base_models:
            try:
                pred = model.predict(X)
                predictions.append(pred)
            except Exception as e:
                logger.warning(f"Model {model.model_name} prediction failed: {e}")
        
        if not predictions:
            raise RuntimeError("No valid predictions from base models")
        
        # Average all predictions
        import numpy as np
        return np.mean(predictions, axis=0)


class ModelRegistry:
    """
    Central registry for all models
    NO hardcoding - models registered from config
    """
    
    def __init__(self, config_path='ML_System/config.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        from storage_manager import SmartStorageManager
        self.storage = SmartStorageManager(config_path)
        
        self.models = {}
        self._register_models()
    
    def _register_models(self):
        """Register all enabled models from config"""
        enabled = self.config['models']['enabled_models']
        
        for model_cfg in enabled:
            if not model_cfg.get('active', True):
                continue
            
            name = model_cfg['name']
            model_config = model_cfg.get('config', {})
            
            # Create model instance
            if name == 'RandomForest':
                self.models[name] = RandomForestModel(model_config, self.storage)
            elif name == 'XGBoost':
                self.models[name] = XGBoostModel(model_config, self.storage)
            elif name == 'LightGBM':
                self.models[name] = LightGBMModel(model_config, self.storage)
            elif name == 'Prophet':
                self.models[name] = ProphetModel(model_config, self.storage)
            elif name == 'IsolationForest':
                self.models[name] = IsolationForestModel(model_config, self.storage)
            
            logger.info(f"Registered model: {name}")
        
        logger.info(f"Total models registered: {len(self.models)}")
    
    def get_model(self, name):
        """Get model by name"""
        return self.models.get(name)
    
    def train_all(self, X_train, y_train, X_val, y_val):
        """Train all registered models"""
        results = {}
        
        for name, model in self.models.items():
            if name == 'IsolationForest':
                # Anomaly detection doesn't need y
                model.train(X_train)
            else:
                try:
                    logger.info(f"Training {name}...")
                    model.train(X_train, y_train, X_val, y_val)
                    results[name] = 'success'
                except Exception as e:
                    logger.error(f"Failed to train {name}: {e}")
                    results[name] = f'failed: {e}'
        
        # Create ensemble from successful models
        successful_models = [m for n, m in self.models.items() 
                           if results.get(n) == 'success' and n != 'IsolationForest']
        
        if len(successful_models) >= 2:
            ensemble = EnsembleModel({}, self.storage, successful_models)
            ensemble.train(X_train, y_train, X_val, y_val)
            self.models['Ensemble'] = ensemble
            results['Ensemble'] = 'success'
        
        return results
    
    def get_best_model(self, task='prediction'):
        """Get best performing model from storage logs"""
        best_name = self.storage.get_best_model(task)
        return self.models.get(best_name)
    
    def list_models(self):
        """List all registered models"""
        return list(self.models.keys())


if __name__ == '__main__':
    # Test model registry
    logging.basicConfig(level=logging.INFO)
    
    registry = ModelRegistry()
    print(f"\n✓ Models registered: {registry.list_models()}")
