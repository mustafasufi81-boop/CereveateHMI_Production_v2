"""
Master BI Orchestrator
Coordinates all BI engines and manages complete analysis workflow
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

from .baseline_engine import AdaptiveBaselineEngine
from .efficiency_engine import EfficiencyAdjustmentEngine
from .delta_scorer import WeightedDeltaScorer
from .availability_engine import AvailabilityProductionEngine
from .influence_engine import InfluenceMapEngine
from .stability_engine import StabilityIndexEngine
from .condition_engine import ConditionScoringEngine
from .loss_engine import LossAttributionEngine
from .config import get_config
from .utils import get_cache

logger = logging.getLogger(__name__)


class MasterBIOrchestrator:
    """
    Orchestrates all BI calculation engines
    Provides unified interface for complete analytics workflow
    """
    
    def __init__(self, config_path: Optional[str] = None, use_cache: bool = True):
        """
        Initialize master orchestrator
        
        Args:
            config_path: Path to configuration file
            use_cache: Whether to use caching
        """
        # Load configuration
        self.config = get_config(config_path)
        
        # Initialize cache
        self.use_cache = use_cache
        if use_cache:
            cache_config = self.config.get_engine_config('cache')
            self.cache = get_cache(
                ttl_seconds=cache_config.get('ttl', 3600),
                max_size=cache_config.get('max_size', 1000)
            )
        
        # Initialize all engines with configuration
        self._initialize_engines()
        
        logger.info("✓ Master BI Orchestrator initialized")
    
    def _initialize_engines(self):
        """Initialize all BI engines with configuration"""
        self.baseline_engine = AdaptiveBaselineEngine(
            self.config.get_engine_config('baseline_engine')
        )
        
        self.efficiency_engine = EfficiencyAdjustmentEngine(
            self.config.get_engine_config('efficiency_engine')
        )
        
        self.delta_scorer = WeightedDeltaScorer(
            self.config.get_engine_config('delta_scorer')
        )
        
        self.availability_engine = AvailabilityProductionEngine(
            self.config.get_engine_config('availability_engine')
        )
        
        self.influence_engine = InfluenceMapEngine(
            self.config.get_engine_config('influence_engine')
        )
        
        self.stability_engine = StabilityIndexEngine()
        
        self.condition_engine = ConditionScoringEngine(
            self.config.get_engine_config('condition_engine')
        )
        
        self.loss_engine = LossAttributionEngine(
            self.config.get_engine_config('loss_engine')
        )
    
    def execute_full_analysis(
        self,
        df: pd.DataFrame,
        production_tag: str,
        influencing_tags: List[str],
        rated_capacity: float
    ) -> Dict:
        """
        Execute complete BI analysis workflow
        
        This is the main entry point replicating the full JS analysis
        
        Args:
            df: DataFrame with all data (must include Timestamp column)
            production_tag: Main production parameter tag
            influencing_tags: List of influencing parameter tags
            rated_capacity: Rated capacity of the plant (MW)
            
        Returns:
            Complete analysis results dictionary
        """
        logger.info("🚀 Starting full BI analysis")
        logger.info(f"  Production tag: {production_tag}")
        logger.info(f"  Influencing tags: {len(influencing_tags)}")
        logger.info(f"  Data points: {len(df)}")
        
        results = {}
        
        # Step 1: Baseline Generation
        logger.info("\n📊 Step 1: Baseline Generation")
        baseline = self._check_cache_or_compute(
            'baseline',
            lambda: self.baseline_engine.calculate_adaptive_baseline(df, production_tag),
            tag=production_tag,
            data_hash=self._hash_dataframe(df[[production_tag, 'Timestamp']])
        )
        results['baseline'] = baseline
        
        if baseline is None:
            logger.error("❌ Failed to calculate baseline - aborting")
            return {'error': 'Baseline calculation failed', 'results': results}
        
        # Step 2: Influence Mapping
        logger.info("\n🔗 Step 2: Influence Mapping")
        influence_map = self._check_cache_or_compute(
            'influence_map',
            lambda: self.influence_engine.compute_influence_map(
                df, production_tag, influencing_tags
            ),
            production_tag=production_tag,
            influencing_tags=tuple(influencing_tags),
            data_hash=self._hash_dataframe(df)
        )
        results['influence_map'] = influence_map
        
        # Step 3: Efficiency Adjustment (for each row)
        logger.info("\n⚙️ Step 3: Efficiency Adjustment")
        df_with_adjusted = self._calculate_efficiency_adjusted(
            df, baseline['value'], influencing_tags
        )
        
        # Step 4: Availability & Production Metrics
        logger.info("\n📈 Step 4: Availability Calculation")
        availability_metrics = self.availability_engine.calculate_availability_production(
            df, production_tag, rated_capacity
        )
        results['availability'] = availability_metrics
        
        # Step 5: Performance Scoring (weighted deltas)
        logger.info("\n🎯 Step 5: Performance Scoring")
        df_with_scores = self.delta_scorer.batch_calculate_scores(
            df_with_adjusted,
            actual_col=production_tag,
            expected_col='adjusted_expected'
        )
        
        # Step 6: Stability Analysis
        logger.info("\n📉 Step 6: Stability Analysis")
        stability = self.stability_engine.calculate_stability_index(
            df[production_tag].values
        )
        results['stability'] = stability
        
        # Step 7: Condition Scoring
        logger.info("\n🟢🟡🔴 Step 7: Condition Scoring")
        df_with_conditions = self.condition_engine.batch_score_conditions(
            df_with_scores,
            parameter_columns=influencing_tags
        )
        
        # Step 8: Loss Attribution
        logger.info("\n🔍 Step 8: Loss Attribution")
        loss_attribution = self._calculate_aggregate_loss_attribution(
            df_with_conditions,
            production_tag,
            influence_map,
            influencing_tags
        )
        results['loss_attribution'] = loss_attribution
        
        # Summary statistics
        logger.info("\n📊 Generating Summary")
        results['summary'] = self._generate_summary(
            df_with_conditions,
            production_tag,
            baseline,
            availability_metrics,
            stability,
            loss_attribution
        )
        
        # Attach processed DataFrame
        results['processed_data'] = df_with_conditions
        
        logger.info("\n✅ Full analysis complete")
        
        return results
    
    def _calculate_efficiency_adjusted(
        self,
        df: pd.DataFrame,
        baseline_value: float,
        influencing_tags: List[str]
    ) -> pd.DataFrame:
        """Calculate efficiency-adjusted expected for all rows"""
        adjusted_expected = []
        
        for idx, row in df.iterrows():
            # Extract current conditions
            conditions = {
                tag: row[tag] for tag in influencing_tags
                if tag in row.index and not pd.isna(row[tag])
            }
            
            # Calculate adjustment
            adjustment = self.efficiency_engine.calculate_adjusted_expected(
                baseline_value,
                conditions
            )
            
            adjusted_expected.append(adjustment['adjusted_expected'])
        
        df['adjusted_expected'] = adjusted_expected
        
        return df
    
    def _calculate_aggregate_loss_attribution(
        self,
        df: pd.DataFrame,
        production_tag: str,
        influence_map: Dict,
        influencing_tags: List[str]
    ) -> Dict:
        """Calculate aggregated loss attribution across all data"""
        attribution_results = []
        
        for idx, row in df.iterrows():
            if pd.isna(row[production_tag]) or pd.isna(row.get('adjusted_expected')):
                continue
            
            conditions = {
                tag: row[tag] for tag in influencing_tags
                if tag in row.index and not pd.isna(row[tag])
            }
            
            attribution = self.loss_engine.attribute_loss(
                actual_production=row[production_tag],
                expected_production=row['adjusted_expected'],
                influence_map=influence_map,
                current_conditions=conditions
            )
            
            attribution_results.append(attribution)
        
        # Generate aggregate summary
        summary = self.loss_engine.generate_loss_summary(attribution_results)
        
        return summary
    
    def _generate_summary(
        self,
        df: pd.DataFrame,
        production_tag: str,
        baseline: Dict,
        availability: Dict,
        stability: Dict,
        loss_attribution: Dict
    ) -> Dict:
        """Generate executive summary of analysis"""
        
        # Calculate actual average production from the selected period
        actual_average_production = float(df[production_tag].mean())
        
        return {
            'current_production': actual_average_production,  # Actual average of selected period
            'baseline_production': baseline['value'],  # Same as current for selected period
            'baseline_confidence': baseline.get('confidence', 1.0),
            'availability_percentage': availability.get('availability', 0),
            'capacity_factor': availability.get('capacity_factor', 0),
            'cumulative_production_mwh': availability.get('cumulative_production', 0),
            'stability_index': stability.get('index', 0),
            'stability_rating': stability.get('rating', 'Unknown'),
            'total_loss_mw': loss_attribution.get('total_loss_sum', 0),
            'top_loss_contributor': (
                loss_attribution['top_chronic_issues'][0][0]
                if loss_attribution.get('top_chronic_issues') else 'Unknown'
            ),
            'data_points': len(df),
            'time_range': {
                'start': df['Timestamp'].min().isoformat() if 'Timestamp' in df.columns else None,
                'end': df['Timestamp'].max().isoformat() if 'Timestamp' in df.columns else None
            }
        }
    
    def _check_cache_or_compute(self, operation: str, compute_func, **kwargs):
        """Check cache or compute result"""
        if not self.use_cache:
            return compute_func()
        
        cached = self.cache.get(operation, **kwargs)
        if cached is not None:
            return cached
        
        result = compute_func()
        self.cache.set(operation, result, **kwargs)
        
        return result
    
    def _hash_dataframe(self, df: pd.DataFrame) -> str:
        """Generate hash of DataFrame for cache key"""
        import hashlib
        
        # Use shape and first/last values as hash
        hash_input = f"{df.shape}_{df.iloc[0].to_json()}_{df.iloc[-1].to_json()}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def invalidate_cache(self, operation: str = None):
        """Invalidate cached results"""
        if self.use_cache:
            self.cache.invalidate(operation)
            logger.info(f"Cache invalidated for {operation or 'all'}")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        if self.use_cache:
            return self.cache.get_stats()
        return {'enabled': False}
