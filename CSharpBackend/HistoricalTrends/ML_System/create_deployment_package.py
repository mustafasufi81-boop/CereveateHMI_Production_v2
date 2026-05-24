"""
Create Deployment Package
Generates production-ready model package for plant EXE deployment
"""

import json
import shutil
import pickle
from pathlib import Path
from datetime import datetime
import pandas as pd
import yaml
import logging

logger = logging.getLogger(__name__)


class DeploymentPackageCreator:
    """Creates deployment package from trained models"""
    
    def __init__(self):
        # Load ML config
        with open('ML_System/config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.models_path = Path('ML_System/Models')
        self.data_path = Path('ML_System/Data')
        self.deployment_path = Path('ModelDeployment')
        
        logger.info("Deployment Package Creator initialized")
    
    def create_package(self, version=None):
        """
        Create complete deployment package
        
        Args:
            version: Package version (auto-generated if None)
        
        Returns:
            Path to created package
        """
        if version is None:
            version = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        package_path = self.deployment_path / f"v{version}"
        
        logger.info(f"Creating deployment package: {package_path}")
        
        # Create directory structure
        self._create_directories(package_path)
        
        # Copy trained models
        self._copy_models(package_path)
        
        # Create parameter configuration
        self._create_parameter_config(package_path)
        
        # Create model metadata
        self._create_model_metadata(package_path)
        
        # Create deployment config
        self._create_deployment_config(package_path, version)
        
        # Create README
        self._create_readme(package_path)
        
        logger.info(f"✓ Deployment package created: {package_path}")
        return package_path
    
    def _create_directories(self, package_path):
        """Create deployment directory structure"""
        dirs = [
            package_path / 'trained_models',
            package_path / 'parameter_config',
            package_path / 'model_metadata',
            package_path / 'scaler_files'
        ]
        
        for dir in dirs:
            dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Created directory structure")
    
    def _copy_models(self, package_path):
        """Copy trained model files"""
        models_dest = package_path / 'trained_models'
        
        if not self.models_path.exists():
            logger.warning("No models directory found")
            return
        
        model_files = list(self.models_path.glob('*.pkl'))
        
        if not model_files:
            logger.warning("No trained models found")
            return
        
        for model_file in model_files:
            dest = models_dest / model_file.name
            shutil.copy2(model_file, dest)
            logger.info(f"Copied model: {model_file.name}")
        
        logger.info(f"Copied {len(model_files)} model files")
    
    def _create_parameter_config(self, package_path):
        """Create parameter configuration files"""
        param_dest = package_path / 'parameter_config'
        
        # Copy parameter importance scores
        param_scores_path = self.data_path / '02_DiscoveredParameters' / 'parameter_importance_scores.csv'
        
        if param_scores_path.exists():
            df = pd.read_csv(param_scores_path)
            
            # Save CSV
            df.to_csv(param_dest / 'parameter_importance_scores.csv', index=False)
            
            # Create top parameters JSON
            top_params = []
            for idx, row in df.iterrows():
                top_params.append({
                    'rank': idx + 1,
                    'tag_name': row['parameter'],
                    'importance': float(row['importance_score']),
                    'correlation': float(row['correlation']) if 'correlation' in row else None,
                    'required': idx < 15  # Top 15 are required
                })
            
            top_params_json = {
                'parameters': top_params,
                'minimum_required': 15,
                'total_available': len(top_params),
                'target_column': self.config['models']['training']['target_column']
            }
            
            with open(param_dest / 'top_parameters.json', 'w') as f:
                json.dump(top_params_json, f, indent=2)
            
            # Create parameter mapping
            param_mapping = {
                'input_parameters': [p['tag_name'] for p in top_params],
                'target_parameter': self.config['models']['training']['target_column'],
                'timestamp_column': 'timestamp'
            }
            
            with open(param_dest / 'parameter_mapping.json', 'w') as f:
                json.dump(param_mapping, f, indent=2)
            
            logger.info(f"Created parameter config with {len(top_params)} parameters")
        else:
            logger.warning("Parameter importance scores not found")
    
    def _create_model_metadata(self, package_path):
        """Create model performance metadata"""
        meta_dest = package_path / 'model_metadata'
        
        # Load performance log
        perf_path = self.data_path / '08_ModelComparison' / 'model_performance_log.csv'
        
        if perf_path.exists():
            df = pd.read_csv(perf_path)
            
            # Save performance CSV
            df.to_csv(meta_dest / 'model_performance.csv', index=False)
            
            # Find best model
            if 'MAE' in df.columns:
                best_idx = df['MAE'].idxmin()
                best_model = df.iloc[best_idx]
                
                best_config = {
                    'primary_model': {
                        'name': best_model['model_name'],
                        'file': f"trained_models/{best_model['model_name']}_v1.pkl",
                        'mae': float(best_model['MAE']),
                        'rmse': float(best_model['RMSE']) if 'RMSE' in best_model else None,
                        'r2': float(best_model['R2']) if 'R2' in best_model else None,
                        'mape': float(best_model['MAPE']) if 'MAPE' in best_model else None,
                        'samples': int(best_model['samples']),
                        'confidence_threshold': 0.85
                    },
                    'fallback_models': []
                }
                
                # Add other models as fallback
                for idx, row in df.iterrows():
                    if idx != best_idx:
                        best_config['fallback_models'].append({
                            'name': row['model_name'],
                            'file': f"trained_models/{row['model_name']}_v1.pkl",
                            'mae': float(row['MAE']) if pd.notna(row['MAE']) else None,
                            'use_if': 'primary_model_fails'
                        })
                
                with open(meta_dest / 'best_model_config.json', 'w') as f:
                    json.dump(best_config, f, indent=2)
                
                logger.info(f"Best model: {best_model['model_name']} (MAE: {best_model['MAE']:.4f})")
            
            # Create ensemble weights (if applicable)
            if len(df) > 1:
                # Calculate weights based on inverse MAE
                if 'MAE' in df.columns:
                    df['inverse_mae'] = 1 / (df['MAE'] + 0.001)
                    total = df['inverse_mae'].sum()
                    df['weight'] = df['inverse_mae'] / total
                    
                    weights = {}
                    for idx, row in df.iterrows():
                        model_name = row['model_name'].replace('Model', '')
                        weights[model_name] = round(float(row['weight']), 4)
                    
                    with open(meta_dest / 'model_weights.json', 'w') as f:
                        json.dump(weights, f, indent=2)
                    
                    logger.info(f"Created ensemble weights for {len(weights)} models")
        else:
            logger.warning("Model performance log not found")
    
    def _create_deployment_config(self, package_path, version):
        """Create master deployment configuration"""
        # Load performance data
        perf_path = self.data_path / '08_ModelComparison' / 'model_performance_log.csv'
        param_path = self.data_path / '02_DiscoveredParameters' / 'parameter_importance_scores.csv'
        
        config = {
            'version': version,
            'created_date': datetime.now().isoformat(),
            'target_column': self.config['models']['training']['target_column']
        }
        
        if perf_path.exists():
            df = pd.read_csv(perf_path)
            if len(df) > 0:
                best_idx = df['MAE'].idxmin() if 'MAE' in df.columns else 0
                best = df.iloc[best_idx]
                
                config.update({
                    'best_model': best['model_name'],
                    'best_model_mae': float(best['MAE']) if 'MAE' in best else None,
                    'best_model_accuracy': round((1 - float(best['MAE']) / 100) * 100, 2) if 'MAE' in best else None,
                    'model_file': f"trained_models/{best['model_name']}_v1.pkl",
                    'total_samples': int(best['samples']) if 'samples' in best else None
                })
        
        if param_path.exists():
            df_params = pd.read_csv(param_path)
            config['parameters_used'] = len(df_params)
        
        config.update({
            'prediction_interval_seconds': 60,
            'retrain_recommended_days': 30,
            'minimum_confidence': 0.70,
            'alert_threshold_mae': 5.0
        })
        
        with open(package_path / 'deployment_config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info("Created deployment configuration")
    
    def _create_readme(self, package_path):
        """Create deployment README"""
        readme_content = f"""# ML Model Deployment Package
**Version**: {package_path.name}
**Created**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📦 Package Contents

### Trained Models (`trained_models/`)
Pre-trained machine learning models ready for production use.

### Parameter Configuration (`parameter_config/`)
- `top_parameters.json`: Which OPC tags to read for predictions
- `parameter_importance_scores.csv`: Full parameter rankings
- `parameter_mapping.json`: Input/output mapping

### Model Metadata (`model_metadata/`)
- `best_model_config.json`: Which model to use in production
- `model_performance.csv`: Performance metrics for all models
- `model_weights.json`: Ensemble model weights

### Deployment Config (`deployment_config.json`)
Master configuration file - read this first!

## 🚀 Deployment Instructions

### Step 1: Copy Package
Copy entire `{package_path.name}` folder to production computer.

### Step 2: Configure Production EXE
Update EXE config to point to:
```
ModelPath: {package_path.name}/deployment_config.json
```

### Step 3: Restart Application
Restart the OPC DA application. It will:
1. Read `deployment_config.json`
2. Load best model from `trained_models/`
3. Start reading parameters from `parameter_config/top_parameters.json`
4. Begin making predictions

## 📊 Model Performance

Load `model_metadata/model_performance.csv` to see accuracy metrics.

## 🔄 Updating Models

To update with new trained models:
1. Generate new deployment package
2. Copy new package to production
3. Update EXE config path
4. Restart application

## ⚠️ Important Notes

- Do NOT modify .pkl files (they are binary model files)
- Keep all JSON files synchronized
- Backup current package before deploying new version
- Test new models in staging environment first

## Support

For questions about this deployment package, contact ML training team.

---
**Auto-generated by DeploymentPackageCreator**
"""
        
        with open(package_path / 'README.txt', 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        logger.info("Created README")


def main():
    """Create deployment package from command line"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create ML model deployment package'
    )
    parser.add_argument('--version', help='Package version (default: auto-generated)')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create package
    creator = DeploymentPackageCreator()
    package_path = creator.create_package(version=args.version)
    
    print(f"\n✅ Deployment package created: {package_path}")
    print("\nPackage contents:")
    print(f"  - Trained models: {len(list((package_path / 'trained_models').glob('*.pkl')))} files")
    print(f"  - Configuration files: {len(list(package_path.glob('*.json')))} files")
    print("\nNext steps:")
    print(f"1. Review {package_path}/deployment_config.json")
    print(f"2. Copy {package_path}/ to production computer")
    print("3. Update EXE configuration")
    print("4. Restart application")


if __name__ == '__main__':
    main()
