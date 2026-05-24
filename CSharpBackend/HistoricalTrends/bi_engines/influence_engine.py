"""
Multi-Parameter Influence Map Engine
Computes correlations, cross-correlations, and impact analysis
"""

import numpy as np
import pandas as pd
from scipy import stats, signal
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class InfluenceMapEngine:
    """
    Computes comprehensive influence maps showing how parameters affect production
    Uses Pearson correlation, rolling correlation, cross-correlation lag, and impact analysis
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize influence map engine
        
        Args:
            config: Configuration with:
                - rolling_window: Window for rolling correlation in hours (default: 24)
                - max_lag: Maximum lag to check in minutes (default: 60)
        """
        config = config or {}
        self.rolling_window = config.get('rolling_window', 24)  # hours
        self.max_lag = config.get('max_lag', 60)  # minutes
        
        logger.info(f"Influence Engine initialized: window={self.rolling_window}h, max_lag={self.max_lag}min")
    
    def compute_influence_map(
        self,
        df: pd.DataFrame,
        primary_tag: str,
        influencing_tags: List[str]
    ) -> Dict[str, Dict]:
        """
        Compute comprehensive influence map
        
        Args:
            df: DataFrame with all tags
            primary_tag: Target tag (e.g., production)
            influencing_tags: List of influencing parameter tags
            
        Returns:
            Dictionary mapping each influencing tag to correlation metrics
        """
        logger.info(f"🔗 Computing influence map for {primary_tag} vs {len(influencing_tags)} parameters")
        
        influence_map = {}
        
        for tag in influencing_tags:
            try:
                correlation = self._compute_correlations(df, primary_tag, tag)
                influence_map[tag] = correlation
                
                logger.info(f"  {tag}: r={correlation['pearson']:.3f}, "
                          f"impact={correlation['impact_percentage']:.2f}%")
            except Exception as e:
                logger.error(f"❌ Failed to compute correlation for {tag}: {e}")
                influence_map[tag] = self._empty_correlation()
        
        logger.info(f"  ✓ Completed influence map calculation")
        
        return influence_map
    
    def _compute_correlations(
        self,
        df: pd.DataFrame,
        primary_tag: str,
        influencing_tag: str
    ) -> Dict:
        """
        Compute multiple correlation metrics between two tags
        
        Args:
            df: DataFrame with both tags
            primary_tag: Primary tag (Y variable)
            influencing_tag: Influencing tag (X variable)
            
        Returns:
            Dictionary with correlation metrics
        """
        # Extract valid pairs
        valid_mask = df[primary_tag].notna() & df[influencing_tag].notna()
        pairs_df = df[valid_mask][[primary_tag, influencing_tag, 'Timestamp']].copy()
        
        if len(pairs_df) < 10:
            return self._empty_correlation()
        
        x = pairs_df[influencing_tag].values
        y = pairs_df[primary_tag].values
        
        # 1. Pearson correlation
        pearson_r, pearson_p = stats.pearsonr(x, y)
        
        # 2. Spearman correlation (non-parametric)
        spearman_r, spearman_p = stats.spearmanr(x, y)
        
        # 3. Rolling correlation
        rolling_r = self._calculate_rolling_correlation(pairs_df, primary_tag, influencing_tag)
        
        # 4. Cross-correlation lag
        lag_minutes, max_corr = self._calculate_cross_correlation_lag(
            pairs_df, primary_tag, influencing_tag
        )
        
        # 5. Impact percentage (linear regression slope)
        impact_pct = self._calculate_impact_percentage(x, y)
        
        # 6. Relationship interpretation
        relationship = self._interpret_correlation(pearson_r)
        
        return {
            'pearson': float(pearson_r),
            'pearson_pvalue': float(pearson_p),
            'spearman': float(spearman_r),
            'spearman_pvalue': float(spearman_p),
            'rolling': float(rolling_r),
            'lag_minutes': int(lag_minutes),
            'lag_correlation': float(max_corr),
            'impact_percentage': float(impact_pct),
            'sample_size': int(len(pairs_df)),
            'relationship': relationship,
            'is_significant': bool(pearson_p < 0.05)
        }
    
    def _calculate_rolling_correlation(
        self,
        pairs_df: pd.DataFrame,
        tag1: str,
        tag2: str
    ) -> float:
        """Calculate most recent rolling window correlation"""
        # Use last N points based on rolling window
        window_size = min(len(pairs_df), self.rolling_window * 60)  # Assume 1-min data
        
        if window_size < 10:
            return 0.0
        
        recent = pairs_df.tail(window_size)
        x = recent[tag2].values
        y = recent[tag1].values
        
        if len(x) < 2:
            return 0.0
        
        r, _ = stats.pearsonr(x, y)
        return r
    
    def _calculate_cross_correlation_lag(
        self,
        pairs_df: pd.DataFrame,
        tag1: str,
        tag2: str
    ) -> Tuple[int, float]:
        """
        Calculate cross-correlation lag
        
        Returns:
            (lag_minutes, max_correlation)
        """
        # Sample uniformly if too many points
        if len(pairs_df) > 10000:
            pairs_df = pairs_df.sample(n=10000, random_state=42).sort_values('Timestamp')
        
        y = pairs_df[tag1].values
        x = pairs_df[tag2].values
        
        # Normalize
        y_norm = (y - np.mean(y)) / (np.std(y) + 1e-10)
        x_norm = (x - np.mean(x)) / (np.std(x) + 1e-10)
        
        # Compute cross-correlation using scipy
        correlation = signal.correlate(y_norm, x_norm, mode='same')
        correlation = correlation / len(y_norm)
        
        # Find peak
        center = len(correlation) // 2
        search_range = min(self.max_lag, center)
        
        search_start = center - search_range
        search_end = center + search_range
        
        search_corr = correlation[search_start:search_end]
        peak_idx = np.argmax(np.abs(search_corr))
        
        lag = peak_idx - search_range
        max_corr = search_corr[peak_idx]
        
        return lag, max_corr
    
    def _calculate_impact_percentage(self, x: np.ndarray, y: np.ndarray) -> float:
        """
        Calculate impact percentage using linear regression slope
        
        Returns percentage change in Y per unit change in X
        """
        # Linear regression
        slope, intercept, _, _, _ = stats.linregress(x, y)
        
        mean_y = np.mean(y)
        
        if mean_y == 0:
            return 0.0
        
        # Impact as percentage change in output per unit change in parameter
        impact_pct = (slope / mean_y) * 100
        
        return impact_pct
    
    def _interpret_correlation(self, r: float) -> str:
        """Interpret correlation strength"""
        abs_r = abs(r)
        
        if abs_r >= 0.9:
            return 'Very Strong'
        elif abs_r >= 0.7:
            return 'Strong'
        elif abs_r >= 0.5:
            return 'Moderate'
        elif abs_r >= 0.3:
            return 'Weak'
        else:
            return 'Very Weak'
    
    def _empty_correlation(self) -> Dict:
        """Return empty correlation result"""
        return {
            'pearson': 0.0,
            'pearson_pvalue': 1.0,
            'spearman': 0.0,
            'spearman_pvalue': 1.0,
            'rolling': 0.0,
            'lag_minutes': 0,
            'lag_correlation': 0.0,
            'impact_percentage': 0.0,
            'sample_size': 0,
            'relationship': 'Unknown',
            'is_significant': False
        }
    
    def find_top_influencers(
        self,
        influence_map: Dict[str, Dict],
        top_n: int = 5,
        sort_by: str = 'pearson'
    ) -> List[Tuple[str, Dict]]:
        """
        Find top influencing parameters
        
        Args:
            influence_map: Complete influence map
            top_n: Number of top influencers to return
            sort_by: Metric to sort by ('pearson', 'spearman', 'impact_percentage')
            
        Returns:
            List of (tag_name, metrics) tuples sorted by influence
        """
        # Filter significant correlations
        significant = {
            tag: metrics for tag, metrics in influence_map.items()
            if metrics.get('is_significant', False)
        }
        
        # Sort by absolute value of metric
        sorted_influencers = sorted(
            significant.items(),
            key=lambda item: abs(item[1].get(sort_by, 0)),
            reverse=True
        )
        
        return sorted_influencers[:top_n]
