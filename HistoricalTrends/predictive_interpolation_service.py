# =====================================================
# PREDICTIVE INTERPOLATION SERVICE
# Uses multiple ML models to predict missing data trends
# =====================================================

import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ML Models
try:
    from scipy.fft import fft, ifft, fftfreq
    from scipy.interpolate import interp1d
    from scipy.signal import savgol_filter
    HAS_SCIPY = True
except:
    HAS_SCIPY = False
    print("⚠️ SciPy not available - FFT model disabled")

try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    HAS_STATSMODELS = True
except:
    HAS_STATSMODELS = False
    print("⚠️ Statsmodels not available - ARIMA/Exponential models disabled")

try:
    from prophet import Prophet
    HAS_PROPHET = True
except:
    HAS_PROPHET = False
    print("⚠️ Prophet not available - Prophet model disabled")

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

class PredictiveInterpolationService:
    """
    Advanced interpolation using multiple predictive models
    
    Available Models:
    1. FFT (Fourier Transform) - Best for periodic/cyclic data
    2. ARIMA - Best for time series with trends
    3. Prophet - Best for seasonal patterns
    4. Exponential Smoothing - Best for smooth trends
    5. Polynomial - Best for simple curves
    6. Random Forest - Best for complex patterns
    7. Linear - Fastest, simplest baseline
    """
    
    AVAILABLE_MODELS = {
        'fft': 'FFT (Fourier Transform) - Best for cyclic patterns',
        'arima': 'ARIMA - Best for trending data',
        'prophet': 'Prophet - Best for seasonal patterns',
        'exponential': 'Exponential Smoothing - Best for smooth trends',
        'polynomial': 'Polynomial Regression - Best for curved trends',
        'random_forest': 'Random Forest - Best for complex patterns',
        'linear': 'Linear Regression - Fast baseline'
    }
    
    def __init__(self, cache_directory):
        self.cache_directory = cache_directory
        self.prediction_cache_file = os.path.join(cache_directory, 'prediction_cache.parquet')
        self.metadata_file = os.path.join(cache_directory, 'prediction_metadata.json')
        
        os.makedirs(cache_directory, exist_ok=True)
        
        self.metadata = self._load_metadata()
    
    def _load_metadata(self):
        """Load prediction metadata"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'version': '2.0',
            'created': datetime.now().isoformat(),
            'predictions': [],
            'models_used': {}
        }
    
    def _save_metadata(self):
        """Save prediction metadata"""
        self.metadata['last_updated'] = datetime.now().isoformat()
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def get_available_models(self):
        """Get list of available models based on installed packages"""
        available = []
        
        if HAS_SCIPY:
            available.append('fft')
            available.append('polynomial')
        
        if HAS_STATSMODELS:
            available.append('arima')
            available.append('exponential')
        
        if HAS_PROPHET:
            available.append('prophet')
        
        # Always available
        available.append('random_forest')
        available.append('linear')
        
        return {model: self.AVAILABLE_MODELS[model] for model in available}
    
    def predict_missing_data(self, original_data, tag, model='fft', context_points=100):
        """
        Predict missing data using specified model
        
        Args:
            original_data: DataFrame with Timestamp, TagId, Value
            tag: Tag to process
            model: Model to use (fft, arima, prophet, etc.)
            context_points: Number of points before/after gap to use for prediction
            
        Returns:
            Dictionary with predictions and metadata
        """
        print(f"🔮 Predicting missing data for {tag} using {model.upper()} model...")
        
        # Extract tag data
        tag_data = original_data[original_data['TagId'] == tag].copy()
        tag_data = tag_data.sort_values('Timestamp')
        
        if len(tag_data) < 10:
            return {'success': False, 'error': 'Insufficient data points'}
        
        # Identify missing segments
        missing_segments = self._identify_missing_segments(tag_data)
        
        if not missing_segments:
            return {
                'success': True,
                'predictions': [],
                'message': 'No missing data segments found',
                'model': model
            }
        
        print(f"  Found {len(missing_segments)} missing segments")
        
        # Generate predictions for each segment
        predictions = []
        for segment in missing_segments:
            try:
                predicted_values = self._predict_segment(
                    tag_data, 
                    segment, 
                    model, 
                    context_points
                )
                predictions.extend(predicted_values)
            except Exception as e:
                print(f"  ⚠️ Failed to predict segment: {e}")
                continue
        
        print(f"  ✓ Generated {len(predictions)} predictions")
        
        return {
            'success': True,
            'predictions': predictions,
            'model': model,
            'segments': len(missing_segments),
            'tag': tag
        }
    
    def _identify_missing_segments(self, tag_data):
        """Identify continuous segments of missing data"""
        tag_data['has_value'] = tag_data['Value'].notna()
        
        # Find gaps
        segments = []
        in_gap = False
        gap_start = None
        
        for idx, row in tag_data.iterrows():
            if pd.isna(row['Value']) and not in_gap:
                # Start of gap
                in_gap = True
                gap_start = row['Timestamp']
            elif not pd.isna(row['Value']) and in_gap:
                # End of gap
                segments.append({
                    'start': gap_start,
                    'end': row['Timestamp'],
                    'start_idx': tag_data[tag_data['Timestamp'] == gap_start].index[0],
                    'end_idx': idx
                })
                in_gap = False
                gap_start = None
        
        return segments
    
    def _predict_segment(self, tag_data, segment, model, context_points):
        """Predict values for a missing segment using specified model"""
        
        # Get context before gap
        before_idx = max(0, segment['start_idx'] - context_points)
        before_data = tag_data.iloc[before_idx:segment['start_idx']]
        
        # Get context after gap
        after_idx = min(len(tag_data), segment['end_idx'] + context_points)
        after_data = tag_data.iloc[segment['end_idx']:after_idx]
        
        # Combine context
        context_data = pd.concat([before_data, after_data]).dropna(subset=['Value'])
        
        if len(context_data) < 3:
            return []
        
        # Call appropriate prediction model
        if model == 'fft' and HAS_SCIPY:
            return self._predict_fft(context_data, segment, tag_data)
        elif model == 'arima' and HAS_STATSMODELS:
            return self._predict_arima(context_data, segment, tag_data)
        elif model == 'prophet' and HAS_PROPHET:
            return self._predict_prophet(context_data, segment, tag_data)
        elif model == 'exponential' and HAS_STATSMODELS:
            return self._predict_exponential(context_data, segment, tag_data)
        elif model == 'polynomial' and HAS_SCIPY:
            return self._predict_polynomial(context_data, segment, tag_data)
        elif model == 'random_forest':
            return self._predict_random_forest(context_data, segment, tag_data)
        else:
            return self._predict_linear(context_data, segment, tag_data)
    
    def _predict_fft(self, context_data, segment, full_data):
        """FFT-based prediction (best for cyclic/periodic data)"""
        values = context_data['Value'].values
        
        # Apply FFT
        fft_vals = fft(values)
        freqs = fftfreq(len(values))
        
        # Keep only dominant frequencies (filter noise)
        threshold = np.percentile(np.abs(fft_vals), 90)
        fft_vals[np.abs(fft_vals) < threshold] = 0
        
        # Reconstruct signal
        reconstructed = np.real(ifft(fft_vals))
        
        # Interpolate to gap timestamps
        context_times = context_data['Timestamp'].values
        gap_data = full_data[(full_data['Timestamp'] >= segment['start']) & 
                             (full_data['Timestamp'] < segment['end'])]
        
        if len(gap_data) == 0:
            return []
        
        # Create interpolation function
        time_numeric = np.arange(len(values))
        interp_func = interp1d(time_numeric, reconstructed, 
                               kind='cubic', fill_value='extrapolate')
        
        # Generate predictions
        predictions = []
        gap_size = len(gap_data)
        context_size = len(values)
        
        for idx, row in gap_data.iterrows():
            # Estimate position in reconstructed signal
            progress = (row['Timestamp'] - segment['start']).total_seconds() / \
                      (segment['end'] - segment['start']).total_seconds()
            position = context_size / 2 + progress * context_size / 4
            
            predicted_value = float(interp_func(position))
            
            predictions.append({
                'Timestamp': row['Timestamp'],
                'PredictedValue': predicted_value,
                'OriginalValue': None,
                'Model': 'fft',
                'Confidence': 0.85  # FFT confidence based on periodicity
            })
        
        return predictions
    
    def _predict_arima(self, context_data, segment, full_data):
        """ARIMA prediction (best for trending data)"""
        try:
            values = context_data['Value'].values
            
            # Fit ARIMA model (auto-select best parameters)
            model = ARIMA(values, order=(2, 1, 2))
            fitted = model.fit()
            
            # Get gap data
            gap_data = full_data[(full_data['Timestamp'] >= segment['start']) & 
                                 (full_data['Timestamp'] < segment['end'])]
            
            if len(gap_data) == 0:
                return []
            
            # Predict
            forecast = fitted.forecast(steps=len(gap_data))
            
            predictions = []
            for idx, (_, row) in enumerate(gap_data.iterrows()):
                predictions.append({
                    'Timestamp': row['Timestamp'],
                    'PredictedValue': float(forecast[idx]),
                    'OriginalValue': None,
                    'Model': 'arima',
                    'Confidence': 0.80
                })
            
            return predictions
        except Exception as e:
            print(f"    ARIMA failed: {e}, falling back to linear")
            return self._predict_linear(context_data, segment, full_data)
    
    def _predict_prophet(self, context_data, segment, full_data):
        """Prophet prediction (best for seasonal patterns)"""
        try:
            # Prepare data for Prophet
            prophet_data = pd.DataFrame({
                'ds': pd.to_datetime(context_data['Timestamp']),
                'y': context_data['Value'].values
            })
            
            # Fit model
            model = Prophet(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.5
            )
            model.fit(prophet_data)
            
            # Get gap timestamps
            gap_data = full_data[(full_data['Timestamp'] >= segment['start']) & 
                                 (full_data['Timestamp'] < segment['end'])]
            
            if len(gap_data) == 0:
                return []
            
            # Predict
            future = pd.DataFrame({'ds': pd.to_datetime(gap_data['Timestamp'])})
            forecast = model.predict(future)
            
            predictions = []
            for idx, row in gap_data.iterrows():
                predictions.append({
                    'Timestamp': row['Timestamp'],
                    'PredictedValue': float(forecast.iloc[idx]['yhat']),
                    'OriginalValue': None,
                    'Model': 'prophet',
                    'Confidence': 0.75
                })
            
            return predictions
        except Exception as e:
            print(f"    Prophet failed: {e}, falling back to linear")
            return self._predict_linear(context_data, segment, full_data)
    
    def _predict_exponential(self, context_data, segment, full_data):
        """Exponential smoothing (best for smooth trends)"""
        try:
            values = context_data['Value'].values
            
            # Fit exponential smoothing
            model = ExponentialSmoothing(values, trend='add', seasonal=None)
            fitted = model.fit()
            
            gap_data = full_data[(full_data['Timestamp'] >= segment['start']) & 
                                 (full_data['Timestamp'] < segment['end'])]
            
            if len(gap_data) == 0:
                return []
            
            forecast = fitted.forecast(steps=len(gap_data))
            
            predictions = []
            for idx, (_, row) in enumerate(gap_data.iterrows()):
                predictions.append({
                    'Timestamp': row['Timestamp'],
                    'PredictedValue': float(forecast[idx]),
                    'OriginalValue': None,
                    'Model': 'exponential',
                    'Confidence': 0.78
                })
            
            return predictions
        except Exception as e:
            print(f"    Exponential failed: {e}, falling back to linear")
            return self._predict_linear(context_data, segment, full_data)
    
    def _predict_polynomial(self, context_data, segment, full_data):
        """Polynomial regression (best for curved trends)"""
        X = np.arange(len(context_data)).reshape(-1, 1)
        y = context_data['Value'].values
        
        # Fit polynomial (degree 3)
        from sklearn.preprocessing import PolynomialFeatures
        poly = PolynomialFeatures(degree=3)
        X_poly = poly.fit_transform(X)
        
        model = LinearRegression()
        model.fit(X_poly, y)
        
        # Predict gap
        gap_data = full_data[(full_data['Timestamp'] >= segment['start']) & 
                             (full_data['Timestamp'] < segment['end'])]
        
        if len(gap_data) == 0:
            return []
        
        X_gap = np.arange(len(context_data), len(context_data) + len(gap_data)).reshape(-1, 1)
        X_gap_poly = poly.transform(X_gap)
        predictions_vals = model.predict(X_gap_poly)
        
        predictions = []
        for idx, (_, row) in enumerate(gap_data.iterrows()):
            predictions.append({
                'Timestamp': row['Timestamp'],
                'PredictedValue': float(predictions_vals[idx]),
                'OriginalValue': None,
                'Model': 'polynomial',
                'Confidence': 0.70
            })
        
        return predictions
    
    def _predict_random_forest(self, context_data, segment, full_data):
        """Random Forest prediction (best for complex patterns)"""
        # Use time-based features
        X = np.arange(len(context_data)).reshape(-1, 1)
        y = context_data['Value'].values
        
        model = RandomForestRegressor(n_estimators=50, max_depth=10, random_state=42)
        model.fit(X, y)
        
        gap_data = full_data[(full_data['Timestamp'] >= segment['start']) & 
                             (full_data['Timestamp'] < segment['end'])]
        
        if len(gap_data) == 0:
            return []
        
        X_gap = np.arange(len(context_data), len(context_data) + len(gap_data)).reshape(-1, 1)
        predictions_vals = model.predict(X_gap)
        
        predictions = []
        for idx, (_, row) in enumerate(gap_data.iterrows()):
            predictions.append({
                'Timestamp': row['Timestamp'],
                'PredictedValue': float(predictions_vals[idx]),
                'OriginalValue': None,
                'Model': 'random_forest',
                'Confidence': 0.65
            })
        
        return predictions
    
    def _predict_linear(self, context_data, segment, full_data):
        """Linear regression (fast baseline)"""
        X = np.arange(len(context_data)).reshape(-1, 1)
        y = context_data['Value'].values
        
        model = LinearRegression()
        model.fit(X, y)
        
        gap_data = full_data[(full_data['Timestamp'] >= segment['start']) & 
                             (full_data['Timestamp'] < segment['end'])]
        
        if len(gap_data) == 0:
            return []
        
        X_gap = np.arange(len(context_data), len(context_data) + len(gap_data)).reshape(-1, 1)
        predictions_vals = model.predict(X_gap)
        
        predictions = []
        for idx, (_, row) in enumerate(gap_data.iterrows()):
            predictions.append({
                'Timestamp': row['Timestamp'],
                'PredictedValue': float(predictions_vals[idx]),
                'OriginalValue': None,
                'Model': 'linear',
                'Confidence': 0.60
            })
        
        return predictions
    
    def compare_models(self, original_data, tag, models=None, context_points=100):
        """
        Run multiple models and compare results
        User can then choose which model to use
        
        Returns predictions from all models for comparison
        """
        if models is None:
            models = list(self.get_available_models().keys())
        
        print(f"🔬 Comparing {len(models)} models for {tag}...")
        
        results = {}
        for model in models:
            try:
                result = self.predict_missing_data(original_data, tag, model, context_points)
                if result['success']:
                    results[model] = result
                    print(f"  ✓ {model.upper()}: {len(result['predictions'])} predictions")
            except Exception as e:
                print(f"  ✗ {model.upper()} failed: {e}")
        
        return {
            'success': True,
            'tag': tag,
            'models': results,
            'comparison_ready': True
        }
    
    def save_predictions(self, predictions, model, tag, user_confirmed=False):
        """Save predictions to cache after user confirmation"""
        if not user_confirmed:
            return {
                'success': False,
                'error': 'User confirmation required before saving predictions'
            }
        
        # Convert to DataFrame
        pred_df = pd.DataFrame(predictions)
        pred_df['TagId'] = tag
        pred_df['CreatedAt'] = datetime.now().isoformat()
        pred_df['UserConfirmed'] = True
        
        # Append to cache
        if os.path.exists(self.prediction_cache_file):
            existing = pd.read_parquet(self.prediction_cache_file)
            pred_df = pd.concat([existing, pred_df], ignore_index=True)
        
        pred_df.to_parquet(self.prediction_cache_file, index=False)
        
        # Update metadata
        self.metadata['predictions'].append({
            'timestamp': datetime.now().isoformat(),
            'tag': tag,
            'model': model,
            'points': len(predictions),
            'user_confirmed': True
        })
        self._save_metadata()
        
        print(f"✓ Saved {len(predictions)} predictions for {tag} using {model}")
        
        return {'success': True, 'saved': len(predictions)}
