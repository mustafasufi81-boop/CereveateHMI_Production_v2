"""
ML System Verification Script
Tests all models and auto-learning components before training
"""

import sys
sys.path.insert(0, './ML_System')

import yaml
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_configuration():
    """Test config.yaml is valid"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Configuration Validation")
    logger.info("=" * 80)
    
    try:
        with open('ML_System/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Check required sections
        required = ['storage', 'data_collection', 'models', 'parameter_discovery', 
                   'feedback', 'processes']
        
        for section in required:
            if section in config:
                logger.info(f"  ✓ {section}: OK")
            else:
                logger.error(f"  ✗ {section}: MISSING")
                return False
        
        # Check enabled models
        enabled_models = [m for m in config['models']['enabled_models'] if m['active']]
        logger.info(f"\n  Enabled Models: {len(enabled_models)}")
        for model in enabled_models:
            logger.info(f"    - {model['name']} ({model['library']})")
        
        logger.info("\n✅ Configuration Valid")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration Error: {e}")
        return False


def test_storage_manager():
    """Test storage manager"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Storage Manager")
    logger.info("=" * 80)
    
    try:
        from storage_manager import SmartStorageManager
        import pandas as pd
        
        storage = SmartStorageManager()
        
        # Test save/load
        test_data = pd.DataFrame({
            'timestamp': [pd.Timestamp.now()],
            'value': [100.0]
        })
        
        storage.save(test_data, '01_RawData', 'test_file')
        logger.info("  ✓ Save: OK")
        
        loaded = storage.load('01_RawData', 'test_file')
        if len(loaded) > 0:
            logger.info("  ✓ Load: OK")
        else:
            logger.error("  ✗ Load: FAILED")
            return False
        
        logger.info("\n✅ Storage Manager Working")
        return True
        
    except Exception as e:
        logger.error(f"❌ Storage Manager Error: {e}")
        return False


def test_model_registry():
    """Test all model implementations"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Model Registry - All 6 Models")
    logger.info("=" * 80)
    
    try:
        from model_registry import (
            RandomForestModel, XGBoostModel, LightGBMModel,
            ProphetModel, IsolationForestModel, EnsembleModel
        )
        from storage_manager import SmartStorageManager
        import numpy as np
        
        storage = SmartStorageManager()
        config = {}
        
        models = [
            ('RandomForest', RandomForestModel),
            ('XGBoost', XGBoostModel),
            ('LightGBM', LightGBMModel),
            ('Prophet', ProphetModel),
            ('IsolationForest', IsolationForestModel),
            ('Ensemble', EnsembleModel)
        ]
        
        for name, ModelClass in models:
            try:
                model = ModelClass(config, storage)
                logger.info(f"  ✓ {name}: Initialized")
            except Exception as e:
                logger.error(f"  ✗ {name}: FAILED - {e}")
                return False
        
        logger.info("\n✅ All 6 Models Available")
        return True
        
    except Exception as e:
        logger.error(f"❌ Model Registry Error: {e}")
        return False


def test_parameter_discovery():
    """Test parameter discovery"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Parameter Discovery")
    logger.info("=" * 80)
    
    try:
        from parameter_discovery import ParameterDiscovery
        import yaml
        
        with open('ML_System/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        discovery = ParameterDiscovery(config)
        logger.info("  ✓ Parameter Discovery: Initialized")
        
        # Check methods exist
        methods = ['discover_important_parameters', 'rank_parameters', 
                  'create_derived_features']
        
        for method in methods:
            if hasattr(discovery, method):
                logger.info(f"  ✓ Method '{method}': Available")
            else:
                logger.error(f"  ✗ Method '{method}': MISSING")
                return False
        
        logger.info("\n✅ Parameter Discovery Working")
        return True
        
    except Exception as e:
        logger.error(f"❌ Parameter Discovery Error: {e}")
        return False


def test_model_trainer():
    """Test model trainer"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 5: Model Trainer")
    logger.info("=" * 80)
    
    try:
        from model_trainer import ModelTrainer
        import yaml
        
        with open('ML_System/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        trainer = ModelTrainer(config)
        logger.info("  ✓ Model Trainer: Initialized")
        
        # Check methods
        methods = ['train_all_models', 'prepare_features', 'load_training_data']
        
        for method in methods:
            if hasattr(trainer, method):
                logger.info(f"  ✓ Method '{method}': Available")
            else:
                logger.error(f"  ✗ Method '{method}': MISSING")
                return False
        
        logger.info("\n✅ Model Trainer Working")
        return True
        
    except Exception as e:
        logger.error(f"❌ Model Trainer Error: {e}")
        return False


def test_prediction_validator():
    """Test prediction validator"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 6: Prediction Validator")
    logger.info("=" * 80)
    
    try:
        from prediction_validator import PredictionValidator
        import yaml
        
        with open('ML_System/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        validator = PredictionValidator(config)
        logger.info("  ✓ Prediction Validator: Initialized")
        
        logger.info("\n✅ Prediction Validator Working")
        return True
        
    except Exception as e:
        logger.error(f"❌ Prediction Validator Error: {e}")
        return False


def test_model_selector():
    """Test model selector"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 7: Model Selector")
    logger.info("=" * 80)
    
    try:
        from model_selector import ModelSelector
        import yaml
        
        with open('ML_System/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        selector = ModelSelector(config)
        logger.info("  ✓ Model Selector: Initialized")
        
        logger.info("\n✅ Model Selector Working")
        return True
        
    except Exception as e:
        logger.error(f"❌ Model Selector Error: {e}")
        return False


def test_weight_adjuster():
    """Test weight adjuster"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 8: Weight Adjuster")
    logger.info("=" * 80)
    
    try:
        from weight_adjuster import WeightAdjuster
        import yaml
        
        with open('ML_System/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        adjuster = WeightAdjuster(config)
        logger.info("  ✓ Weight Adjuster: Initialized")
        
        logger.info("\n✅ Weight Adjuster Working")
        return True
        
    except Exception as e:
        logger.error(f"❌ Weight Adjuster Error: {e}")
        return False


def main():
    """Run all verification tests"""
    
    print("\n" + "=" * 80)
    print("ML SYSTEM VERIFICATION - ALL COMPONENTS")
    print("=" * 80)
    print("Testing all models and auto-learning components...")
    print("=" * 80)
    
    tests = [
        ("Configuration", test_configuration),
        ("Storage Manager", test_storage_manager),
        ("Model Registry (6 Models)", test_model_registry),
        ("Parameter Discovery", test_parameter_discovery),
        ("Model Trainer", test_model_trainer),
        ("Prediction Validator", test_prediction_validator),
        ("Model Selector", test_model_selector),
        ("Weight Adjuster", test_weight_adjuster),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"\n❌ {name} Test Failed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("=" * 80)
    print(f"Results: {passed}/{total} tests passed ({(passed/total*100):.0f}%)")
    print("=" * 80)
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED - System Ready for Training!")
        print("\nNext Steps:")
        print("1. Load historical data: python load_historical_data_for_ml.py")
        print("2. Start ML system: cd ML_System && python background_process_manager.py")
        return True
    else:
        print("\n❌ SOME TESTS FAILED - Fix issues before training")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
