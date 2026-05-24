"""
Optimization Experimenter - Safely tests parameter optimizations
Learns which changes improve performance
"""

import pandas as pd
import numpy as np
from datetime import datetime
import logging
from storage_manager import SmartStorageManager

logger = logging.getLogger(__name__)


class OptimizationExperimenter:
    """
    Runs safe optimization experiments
    Tests parameter changes and learns from results
    """
    
    def __init__(self, config):
        self.config = config
        self.storage = SmartStorageManager()
        
        self.enabled = config['optimization']['enable_auto_optimization']
        self.max_change_pct = config['optimization']['max_change_percentage']
        self.min_improvement = config['optimization']['min_improvement_percentage']
        self.experiment_duration = config['optimization']['experiment_duration_minutes']
        
        if not self.enabled:
            logger.info("Optimization Experimenter DISABLED in config")
        else:
            logger.info("Optimization Experimenter initialized")
    
    def get_baseline_performance(self):
        """Get current baseline performance"""
        try:
            # Load recent raw data
            files = self.storage.list_files('01_RawData')
            
            if not files:
                return None
            
            # Load most recent file
            latest = files[-1]
            df = self.storage.load('01_RawData', latest.stem)
            
            if 'Load' not in df.columns:
                return None
            
            # Calculate baseline metrics
            baseline = {
                'avg_load': df['Load'].mean(),
                'max_load': df['Load'].max(),
                'min_load': df['Load'].min(),
                'std_load': df['Load'].std(),
                'timestamp': datetime.now()
            }
            
            return baseline
            
        except Exception as e:
            logger.error(f"Error getting baseline: {e}")
            return None
    
    def generate_safe_experiment(self, baseline):
        """
        Generate a safe parameter change experiment
        Changes are small and reversible
        """
        # This is a placeholder - actual implementation would:
        # 1. Load discovered important parameters
        # 2. Identify parameters that can be safely changed
        # 3. Generate small changes within safety limits
        # 4. Create experiment plan
        
        experiment = {
            'experiment_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'baseline_load': baseline['avg_load'],
            'proposed_changes': [],
            'expected_improvement': 0,
            'risk_level': 'low',
            'duration_minutes': self.experiment_duration
        }
        
        logger.info(f"Generated experiment: {experiment['experiment_id']}")
        return experiment
    
    def run_safe_experiment(self):
        """
        Main experiment method
        Only runs if enabled and conditions are safe
        """
        if not self.enabled:
            logger.debug("Optimization experiments disabled")
            return False
        
        logger.info("Checking if safe to run optimization experiment...")
        
        # Get baseline
        baseline = self.get_baseline_performance()
        
        if baseline is None:
            logger.warning("Could not establish baseline, skipping experiment")
            return False
        
        # Generate experiment
        experiment = self.generate_safe_experiment(baseline)
        
        # Save experiment plan
        exp_df = pd.DataFrame([experiment])
        self.storage.save(exp_df, '07_OptimizationExperiments', 
                         'parameter_change_log')
        
        logger.info("Optimization experiment logged (execution would happen here)")
        
        # Actual execution would go here in production
        # For now, just log the intent
        
        return True


if __name__ == '__main__':
    # Test optimization experimenter
    logging.basicConfig(level=logging.INFO)
    
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    experimenter = OptimizationExperimenter(config)
    
    print("Testing optimization experimenter...")
    success = experimenter.run_safe_experiment()
    
    if success:
        print("✓ Experiment logged")
    else:
        print("✗ Experiments disabled or failed")
