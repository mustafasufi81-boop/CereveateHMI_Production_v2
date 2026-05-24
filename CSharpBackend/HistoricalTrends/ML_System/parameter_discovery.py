"""
Parameter Discovery Engine
Automatically discovers which parameters matter most
NO hardcoded parameter lists - learns from data
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from storage_manager import SmartStorageManager
from sklearn.feature_selection import mutual_info_regression, SelectKBest, f_regression
from sklearn.decomposition import PCA
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


class ParameterDiscovery:
    """
    Discovers important parameters from raw data
    Uses multiple statistical methods to rank importance
    """
    
    def __init__(self, config):
        self.config = config
        self.storage = SmartStorageManager()
        
        self.min_correlation = config['parameter_discovery']['min_correlation_threshold']
        self.min_variance = config['parameter_discovery']['min_variance_threshold']
        self.min_availability = config['parameter_discovery']['min_data_availability']
        self.target_column = config['parameter_discovery'].get('target_column', 'Load')
        
        logger.info(f"Parameter Discovery Engine initialized (target: {self.target_column})")
    
    def load_recent_data(self, days=30):
        """Load recent data for analysis"""
        try:
            # Get list of raw data files
            files = self.storage.list_files('01_RawData')
            
            if not files:
                logger.warning("No raw data files found")
                return None
            
            # Load last N days
            cutoff_date = datetime.now() - timedelta(days=days)
            
            dfs = []
            for f in files:
                try:
                    # Extract date from filename
                    date_str = f.stem.split('_')[-1]
                    file_date = datetime.strptime(date_str, '%Y%m%d')
                    
                    if file_date >= cutoff_date:
                        df = self.storage.load('01_RawData', f.stem)
                        dfs.append(df)
                except Exception as e:
                    logger.debug(f"Skipping file {f}: {e}")
            
            if not dfs:
                logger.warning("No recent data found")
                return None
            
            # Combine all data
            combined = pd.concat(dfs, ignore_index=True)
            logger.info(f"Loaded {len(combined)} rows from {len(dfs)} files")
            
            return combined
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return None
    
    def filter_valid_parameters(self, df):
        """
        Filter out invalid parameters
        Returns only parameters with sufficient data quality
        """
        valid_params = []
        
        for col in df.columns:
            if col == 'timestamp':
                continue
            
            # Check data availability (non-null percentage)
            availability = df[col].notna().sum() / len(df)
            
            if availability < self.min_availability:
                logger.debug(f"Dropped {col}: low availability ({availability:.1%})")
                continue
            
            # Check if numeric
            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.debug(f"Dropped {col}: non-numeric")
                continue
            
            # Check variance (constant values are useless)
            variance = df[col].var()
            if variance < self.min_variance:
                logger.debug(f"Dropped {col}: low variance ({variance:.4f})")
                continue
            
            valid_params.append(col)
        
        logger.info(f"Valid parameters: {len(valid_params)} / {len(df.columns) - 1}")
        return valid_params
    
    def calculate_correlations(self, df, target_col=None):
        """
        Calculate correlations with target variable
        Uses multiple correlation methods
        """
        if target_col is None:
            target_col = self.target_column
        
        if target_col not in df.columns:
            logger.warning(f"Target column {target_col} not found")
            return {}
        
        correlations = {}
        
        for col in df.columns:
            if col in ['timestamp', target_col]:
                continue
            
            try:
                # Pearson correlation
                pearson = df[col].corr(df[target_col])
                
                # Spearman correlation (rank-based, robust to outliers)
                spearman, _ = spearmanr(df[col].dropna(), df[target_col].dropna())
                
                # Average correlation
                avg_corr = (abs(pearson) + abs(spearman)) / 2
                
                correlations[col] = {
                    'pearson': pearson,
                    'spearman': spearman,
                    'average': avg_corr
                }
                
            except Exception as e:
                logger.debug(f"Correlation failed for {col}: {e}")
        
        return correlations
    
    def calculate_mutual_information(self, df, target_col=None, top_n=50):
        if target_col is None:
            target_col = self.target_column
        """
        Calculate mutual information scores
        Captures non-linear relationships
        """
        if target_col not in df.columns:
            return {}
        
        try:
            # Prepare features
            features = [c for c in df.columns if c not in ['timestamp', target_col]]
            X = df[features].fillna(0)
            y = df[target_col].fillna(0)
            
            # Calculate mutual information
            mi_scores = mutual_info_regression(X, y, random_state=42)
            
            # Create dict
            mi_dict = {features[i]: mi_scores[i] for i in range(len(features))}
            
            # Sort and take top N
            sorted_mi = sorted(mi_dict.items(), key=lambda x: x[1], reverse=True)
            top_mi = dict(sorted_mi[:top_n])
            
            logger.info(f"Calculated mutual information for {len(features)} parameters")
            return top_mi
            
        except Exception as e:
            logger.error(f"Mutual information calculation failed: {e}")
            return {}
    
    def calculate_feature_importance(self, df, target_col=None):
        if target_col is None:
            target_col = self.target_column
        """
        Calculate feature importance using F-regression
        Fast statistical test
        """
        if target_col not in df.columns:
            return {}
        
        try:
            features = [c for c in df.columns if c not in ['timestamp', target_col]]
            X = df[features].fillna(0)
            y = df[target_col].fillna(0)
            
            # F-test
            selector = SelectKBest(f_regression, k='all')
            selector.fit(X, y)
            
            # Get scores
            importance_dict = {features[i]: selector.scores_[i] 
                             for i in range(len(features))}
            
            logger.info(f"Calculated F-scores for {len(features)} parameters")
            return importance_dict
            
        except Exception as e:
            logger.error(f"Feature importance calculation failed: {e}")
            return {}
    
    def remove_multicollinear_parameters(self, df, rankings, threshold=0.90):
        """
        Remove highly correlated (redundant) parameters
        Simple approach: If correlation > threshold, keep only better one
        """
        params = list(rankings.keys())
        
        # Calculate correlation matrix for all parameters
        param_cols = [p for p in params if p in df.columns]
        corr_matrix = df[param_cols].corr().abs()
        
        # Find pairs with high correlation
        redundant = set()
        
        for i, param1 in enumerate(param_cols):
            if param1 in redundant:
                continue
            
            for param2 in param_cols[i+1:]:
                if param2 in redundant:
                    continue
                
                correlation = corr_matrix.loc[param1, param2]
                
                if correlation > threshold:
                    # Keep the one with higher importance
                    score1 = rankings[param1]['final_score']
                    score2 = rankings[param2]['final_score']
                    
                    if score1 >= score2:
                        redundant.add(param2)
                        logger.info(f"Removed {param2} (corr={correlation:.2f} with {param1}, kept higher importance)")
                    else:
                        redundant.add(param1)
                        logger.info(f"Removed {param1} (corr={correlation:.2f} with {param2}, kept higher importance)")
                        break  # param1 removed, move to next
        
        # Remove redundant parameters from rankings
        cleaned_rankings = {k: v for k, v in rankings.items() if k not in redundant}
        
        logger.info(f"Multi-collinearity check: Removed {len(redundant)} redundant parameters")
        logger.info(f"Final parameter count: {len(cleaned_rankings)}")
        
        return cleaned_rankings
    
    def rank_parameters(self, correlations, mi_scores, f_scores):
        """
        Combine all methods to create final ranking
        Multi-method consensus
        """
        all_params = set()
        all_params.update(correlations.keys())
        all_params.update(mi_scores.keys())
        all_params.update(f_scores.keys())
        
        rankings = {}
        
        for param in all_params:
            scores = []
            
            # Correlation score (0-1)
            if param in correlations:
                corr_score = correlations[param]['average']
                scores.append(corr_score)
            
            # Mutual information (normalize to 0-1)
            if param in mi_scores:
                mi_max = max(mi_scores.values()) if mi_scores else 1
                mi_score = mi_scores[param] / mi_max if mi_max > 0 else 0
                scores.append(mi_score)
            
            # F-score (normalize to 0-1)
            if param in f_scores:
                f_max = max(f_scores.values()) if f_scores else 1
                f_score = f_scores[param] / f_max if f_max > 0 else 0
                scores.append(f_score)
            
            # Average all scores
            final_score = np.mean(scores) if scores else 0
            
            rankings[param] = {
                'final_score': final_score,
                'correlation': correlations.get(param, {}).get('average', 0),
                'mi_score': mi_scores.get(param, 0),
                'f_score': f_scores.get(param, 0),
                'num_methods': len(scores)
            }
        
        # Sort by final score
        sorted_rankings = sorted(rankings.items(), 
                               key=lambda x: x[1]['final_score'], 
                               reverse=True)
        
        return dict(sorted_rankings)
    
    def discover_and_rank(self):
        """
        Main discovery method
        Discovers and ranks all parameters
        """
        logger.info("Starting parameter discovery...")
        
        # Load recent data
        df = self.load_recent_data(days=30)
        
        if df is None or len(df) < 100:
            logger.warning("Insufficient data for discovery")
            return False
        
        # Filter valid parameters
        valid_params = self.filter_valid_parameters(df)
        
        if not valid_params:
            logger.warning("No valid parameters found")
            return False
        
        # Keep only valid columns
        df_clean = df[['timestamp'] + valid_params].copy()
        
        # Calculate different importance metrics
        logger.info("Calculating correlations...")
        correlations = self.calculate_correlations(df_clean)
        
        logger.info("Calculating mutual information...")
        mi_scores = self.calculate_mutual_information(df_clean)
        
        logger.info("Calculating feature importance...")
        f_scores = self.calculate_feature_importance(df_clean)
        
        # Combine and rank
        logger.info("Ranking parameters...")
        rankings = self.rank_parameters(correlations, mi_scores, f_scores)
        
        # Remove multi-collinear parameters (simple redundancy removal)
        logger.info("Checking for multi-collinearity...")
        rankings = self.remove_multicollinear_parameters(df_clean, rankings, threshold=0.90)
        
        # Save results
        rankings_df = pd.DataFrame([
            {
                'parameter': param,
                'importance_score': data['final_score'],
                'correlation': data['correlation'],
                'mutual_info': data['mi_score'],
                'f_score': data['f_score'],
                'methods_used': data['num_methods'],
                'discovered_at': datetime.now()
            }
            for param, data in rankings.items()
        ])
        
        self.storage.save(rankings_df, '02_DiscoveredParameters', 
                         'parameter_importance_scores')
        
        # Log top 10
        logger.info("Top 10 most important parameters:")
        for i, (param, data) in enumerate(list(rankings.items())[:10], 1):
            logger.info(f"  {i}. {param}: {data['final_score']:.4f}")
        
        logger.info(f"Parameter discovery complete: {len(rankings)} parameters ranked")
        return True


if __name__ == '__main__':
    # Test parameter discovery
    logging.basicConfig(level=logging.INFO)
    
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    discovery = ParameterDiscovery(config)
    
    print("Testing parameter discovery...")
    success = discovery.discover_and_rank()
    
    if success:
        print("✓ Parameter discovery successful")
    else:
        print("✗ Parameter discovery failed")
