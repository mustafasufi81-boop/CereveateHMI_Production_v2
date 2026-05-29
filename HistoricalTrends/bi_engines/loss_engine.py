"""
Production Loss Attribution Engine
Attributes production losses to specific influencing parameters
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class LossAttributionEngine:
    """
    Attributes production losses to specific root causes
    Uses correlation strength and impact factors to determine contribution
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize loss attribution engine
        
        Args:
            config: Configuration dictionary
                - top_n_contributors: Number of top contributors to return (default: 5)
        """
        config = config or {}
        self.top_n_contributors = config.get('top_n_contributors', 5)
        
        logger.info("Loss Attribution Engine initialized")
    
    def attribute_loss(
        self,
        actual_production: float,
        expected_production: float,
        influence_map: Dict[str, Dict],
        current_conditions: Dict[str, float]
    ) -> Dict:
        """
        Attribute production loss to specific causes
        
        Args:
            actual_production: Actual production value (MW)
            expected_production: Expected production value (MW)
            influence_map: Influence map from InfluenceMapEngine
            current_conditions: Current parameter values
            
        Returns:
            Dictionary with total loss and attributed losses
        """
        logger.info("🔍 Attributing production losses")
        
        # Ensure numeric types
        actual_production = float(actual_production) if actual_production is not None else 0.0
        expected_production = float(expected_production) if expected_production is not None else 0.0
        current_conditions = {k: float(v) if v is not None else 0.0 for k, v in current_conditions.items()}
        
        total_delta = expected_production - actual_production
        
        if total_delta <= 0:
            logger.info("  ✓ No loss - operating at or above expected")
            return {
                'total_loss': 0.0,
                'attribution': {},
                'unattributed_loss': 0.0,
                'top_contributors': []
            }
        
        # Calculate loss contribution for each parameter
        attribution = {}
        total_attributed = 0.0
        
        for param, influence in influence_map.items():
            if param not in current_conditions:
                continue
            
            # Extract correlation and impact
            correlation = abs(influence.get('pearson', 0))
            impact_pct = abs(influence.get('impact_percentage', 0))
            
            # Skip weak/insignificant correlations
            if not influence.get('is_significant', False) or correlation < 0.1:
                continue
            
            # Loss contribution = total_delta × correlation × impact_factor
            # Impact factor normalized to 0-1 range
            impact_factor = min(impact_pct / 100, 1.0)
            
            loss_contribution = total_delta * correlation * impact_factor
            
            attribution[param] = {
                'loss_amount': float(loss_contribution),
                'loss_percentage': float((loss_contribution / total_delta) * 100),
                'correlation': float(correlation),
                'impact': float(impact_pct),
                'current_value': float(current_conditions[param]),
                'is_significant': influence.get('is_significant', False)
            }
            
            total_attributed += loss_contribution
        
        # Normalize if over-attributed
        if total_attributed > total_delta:
            normalization_factor = total_delta / total_attributed
            
            for param in attribution:
                attribution[param]['loss_amount'] *= normalization_factor
                attribution[param]['loss_percentage'] *= normalization_factor
            
            total_attributed = total_delta
        
        # Calculate unattributed loss
        unattributed = total_delta - total_attributed
        
        # Get top contributors
        top_contributors = self._get_top_contributors(attribution, self.top_n_contributors)
        
        logger.info(f"  ✓ Total Loss: {total_delta:.2f} MW")
        logger.info(f"  ✓ Attributed: {total_attributed:.2f} MW ({(total_attributed/total_delta)*100:.1f}%)")
        logger.info(f"  ✓ Unattributed: {unattributed:.2f} MW ({(unattributed/total_delta)*100:.1f}%)")
        logger.info("  Top Contributors:")
        for param, data in top_contributors:
            logger.info(f"    {param}: {data['loss_amount']:.2f} MW ({data['loss_percentage']:.1f}%)")
        
        return {
            'total_loss': float(total_delta),
            'attributed_loss': float(total_attributed),
            'unattributed_loss': float(unattributed),
            'attribution': attribution,
            'top_contributors': [
                {'parameter': param, **data} 
                for param, data in top_contributors
            ]
        }
    
    def batch_attribute_losses(
        self,
        df: pd.DataFrame,
        actual_col: str,
        expected_col: str,
        influence_map: Dict[str, Dict],
        parameter_columns: List[str]
    ) -> pd.DataFrame:
        """
        Attribute losses for all rows in DataFrame
        
        Args:
            df: Input DataFrame
            actual_col: Column name for actual production
            expected_col: Column name for expected production
            influence_map: Influence map for all parameters
            parameter_columns: List of parameter column names
            
        Returns:
            DataFrame with added attribution columns
        """
        logger.info(f"📊 Batch attributing losses for {len(df)} rows")
        
        results = []
        
        for idx, row in df.iterrows():
            actual = row[actual_col]
            expected = row[expected_col]
            
            # Extract current conditions
            current_conditions = {}
            for param in parameter_columns:
                if param in row.index and not pd.isna(row[param]):
                    current_conditions[param] = row[param]
            
            # Attribute loss
            attribution = self.attribute_loss(
                actual,
                expected,
                influence_map,
                current_conditions
            )
            
            # Extract top contributor for this row
            if attribution['top_contributors']:
                top = attribution['top_contributors'][0]
                top_param = top['parameter']
                top_contribution = top['loss_amount']
            else:
                top_param = 'Unknown'
                top_contribution = 0.0
            
            results.append({
                'total_loss': attribution['total_loss'],
                'attributed_loss': attribution['attributed_loss'],
                'unattributed_loss': attribution['unattributed_loss'],
                'top_loss_contributor': top_param,
                'top_contribution_mw': top_contribution
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"  ✓ Completed batch loss attribution")
        
        return pd.concat([df.reset_index(drop=True), result_df], axis=1)
    
    def _get_top_contributors(
        self,
        attribution: Dict[str, Dict],
        top_n: int
    ) -> List[Tuple[str, Dict]]:
        """Get top N loss contributors sorted by loss amount"""
        sorted_attribution = sorted(
            attribution.items(),
            key=lambda item: item[1]['loss_amount'],
            reverse=True
        )
        
        return sorted_attribution[:top_n]
    
    def generate_loss_summary(
        self,
        attribution_results: List[Dict]
    ) -> Dict:
        """
        Generate aggregated loss summary from multiple attribution results
        
        Args:
            attribution_results: List of attribution dictionaries
            
        Returns:
            Aggregated summary with total losses per parameter
        """
        aggregated = {}
        total_loss_sum = 0.0
        
        for result in attribution_results:
            total_loss_sum += result['total_loss']
            
            for param, data in result['attribution'].items():
                if param not in aggregated:
                    aggregated[param] = {
                        'total_loss': 0.0,
                        'occurrences': 0,
                        'avg_correlation': 0.0,
                        'avg_impact': 0.0
                    }
                
                aggregated[param]['total_loss'] += data['loss_amount']
                aggregated[param]['occurrences'] += 1
                aggregated[param]['avg_correlation'] += data['correlation']
                aggregated[param]['avg_impact'] += data['impact']
        
        # Calculate averages
        for param in aggregated:
            count = aggregated[param]['occurrences']
            aggregated[param]['avg_correlation'] /= count
            aggregated[param]['avg_impact'] /= count
            aggregated[param]['percentage_of_total'] = \
                (aggregated[param]['total_loss'] / total_loss_sum * 100) if total_loss_sum > 0 else 0
        
        # Sort by total loss
        sorted_summary = sorted(
            aggregated.items(),
            key=lambda item: item[1]['total_loss'],
            reverse=True
        )
        
        return {
            'total_loss_sum': float(total_loss_sum),
            'parameter_summary': dict(sorted_summary),
            'top_chronic_issues': sorted_summary[:self.top_n_contributors]
        }
