"""
Industrial BI Calculation Engine - Python Backend
PRODUCTION-GRADE ARCHITECTURE:
- ZERO hardcoded values (all from config/user)
- Concurrent user support (thread-safe, session isolation)
- Zero-lag performance (caching, vectorized NumPy, parallel processing)
- Modular structure (separate files per engine)
"""

__version__ = "2.0.0"
__author__ = "Cereveate Tech"

from .baseline_engine import AdaptiveBaselineEngine
from .efficiency_engine import EfficiencyAdjustmentEngine
from .delta_scorer import WeightedDeltaScorer
from .availability_engine import AvailabilityProductionEngine
from .influence_engine import InfluenceMapEngine
from .stability_engine import StabilityIndexEngine
from .condition_engine import ConditionScoringEngine
from .loss_engine import LossAttributionEngine

__all__ = [
    'AdaptiveBaselineEngine',
    'EfficiencyAdjustmentEngine',
    'WeightedDeltaScorer',
    'AvailabilityProductionEngine',
    'InfluenceMapEngine',
    'StabilityIndexEngine',
    'ConditionScoringEngine',
    'LossAttributionEngine'
]
