"""
Background Process Manager
Runs all ML processes asynchronously without blocking system
Uses asyncio for non-blocking operation
"""

import asyncio
import logging
from datetime import datetime, timedelta
import yaml
from pathlib import Path
import signal
import sys

logger = logging.getLogger(__name__)


class BackgroundProcessManager:
    """
    Manages all background ML processes
    Everything runs async - ZERO system load/blocking
    """
    
    def __init__(self, config_path='ML_System/config.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.running = False
        self.tasks = []
        
        # Setup logging
        log_level = getattr(logging, self.config['logging']['console_level'])
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        logger.info("Background Process Manager initialized")
    
    async def data_collector_loop(self):
        """Continuously collect data from OPC/sensors"""
        from data_collector import DataCollector
        
        collector = DataCollector(self.config)
        interval = self.config['processes']['data_collector']['interval_seconds']
        
        logger.info(f"Data Collector started (interval: {interval}s)")
        
        while self.running:
            try:
                # Collect data asynchronously
                await asyncio.to_thread(collector.collect_and_store)
                
                # Sleep without blocking
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Data collector error: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    async def parameter_discovery_loop(self):
        """Discover important parameters from data"""
        from parameter_discovery import ParameterDiscovery
        
        discovery = ParameterDiscovery(self.config)
        interval_hours = self.config['processes']['parameter_discovery']['interval_hours']
        interval_seconds = interval_hours * 3600
        
        logger.info(f"Parameter Discovery started (interval: {interval_hours}h)")
        
        while self.running:
            try:
                # Run discovery asynchronously
                await asyncio.to_thread(discovery.discover_and_rank)
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Parameter discovery error: {e}")
                await asyncio.sleep(3600)  # Retry after 1 hour
    
    async def model_trainer_loop(self):
        """Train all models periodically"""
        from model_trainer import ModelTrainer
        
        trainer = ModelTrainer(self.config)
        interval_hours = self.config['processes']['model_trainer']['interval_hours']
        interval_seconds = interval_hours * 3600
        
        # Wait for initial training period
        min_days = self.config['models']['training']['initial_training_days']
        logger.info(f"Model Trainer will start after {min_days} days of data collection")
        
        # Check if we have enough data
        while self.running:
            try:
                if await asyncio.to_thread(trainer.has_sufficient_data):
                    logger.info("Sufficient data available, starting training loop")
                    break
                else:
                    logger.info(f"Waiting for {min_days} days of data...")
                    await asyncio.sleep(86400)  # Check daily
            except Exception as e:
                logger.error(f"Data check error: {e}")
                await asyncio.sleep(3600)
        
        logger.info(f"Model Trainer started (interval: {interval_hours}h)")
        
        while self.running:
            try:
                # Train all models asynchronously
                await asyncio.to_thread(trainer.train_all_models)
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Model trainer error: {e}")
                await asyncio.sleep(7200)  # Retry after 2 hours
    
    async def prediction_validator_loop(self):
        """Validate predictions against actual results"""
        from prediction_validator import PredictionValidator
        
        validator = PredictionValidator(self.config)
        interval_hours = self.config['processes']['prediction_validator']['interval_hours']
        interval_seconds = interval_hours * 3600
        
        logger.info(f"Prediction Validator started (interval: {interval_hours}h)")
        
        while self.running:
            try:
                # Validate predictions asynchronously
                await asyncio.to_thread(validator.validate_all_predictions)
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Prediction validator error: {e}")
                await asyncio.sleep(3600)
    
    async def weight_adjuster_loop(self):
        """Adjust model weights based on feedback"""
        from weight_adjuster import WeightAdjuster
        
        adjuster = WeightAdjuster(self.config)
        interval_hours = self.config['processes']['weight_adjuster']['interval_hours']
        interval_seconds = interval_hours * 3600
        
        logger.info(f"Weight Adjuster started (interval: {interval_hours}h)")
        
        while self.running:
            try:
                # Adjust weights asynchronously
                await asyncio.to_thread(adjuster.adjust_weights_from_feedback)
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Weight adjuster error: {e}")
                await asyncio.sleep(3600)
    
    async def optimization_experimenter_loop(self):
        """Run optimization experiments"""
        from optimization_experimenter import OptimizationExperimenter
        
        if not self.config['optimization']['enable_auto_optimization']:
            logger.info("Optimization Experimenter disabled in config")
            return
        
        experimenter = OptimizationExperimenter(self.config)
        interval_hours = self.config['processes']['optimization_experimenter']['interval_hours']
        interval_seconds = interval_hours * 3600
        
        logger.info(f"Optimization Experimenter started (interval: {interval_hours}h)")
        
        while self.running:
            try:
                # Run experiments asynchronously
                await asyncio.to_thread(experimenter.run_safe_experiment)
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Optimization experimenter error: {e}")
                await asyncio.sleep(7200)
    
    async def model_selector_loop(self):
        """Select best performing models"""
        from model_selector import ModelSelector
        
        selector = ModelSelector(self.config)
        interval_days = self.config['processes']['model_selector']['interval_days']
        interval_seconds = interval_days * 86400
        
        logger.info(f"Model Selector started (interval: {interval_days} days)")
        
        while self.running:
            try:
                # Select best models asynchronously
                await asyncio.to_thread(selector.select_best_models)
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Model selector error: {e}")
                await asyncio.sleep(86400)
    
    async def cleanup_loop(self):
        """Periodic cleanup of old data"""
        from storage_manager import SmartStorageManager
        
        storage = SmartStorageManager()
        
        logger.info("Cleanup task started (runs daily)")
        
        while self.running:
            try:
                # Cleanup old data
                await asyncio.to_thread(storage.cleanup_old_data)
                
                # Run daily
                await asyncio.sleep(86400)
                
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(86400)
    
    async def health_monitor_loop(self):
        """Monitor system health and log stats"""
        from storage_manager import SmartStorageManager
        
        storage = SmartStorageManager()
        
        logger.info("Health Monitor started (runs hourly)")
        
        while self.running:
            try:
                # Get and log storage stats
                stats = await asyncio.to_thread(storage.get_storage_stats)
                
                logger.info(f"System Health: {stats['mode']}")
                for cat, info in stats['categories'].items():
                    if info['file_count'] > 0:
                        logger.debug(f"  {cat}: {info['file_count']} files, {info['total_size_mb']} MB")
                
                # Run hourly
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(3600)
    
    def start_all_processes(self):
        """Start all enabled background processes"""
        self.running = True
        
        process_config = self.config['processes']
        
        # Create tasks for enabled processes
        if process_config['data_collector']['enabled']:
            self.tasks.append(asyncio.create_task(self.data_collector_loop()))
        
        if process_config['parameter_discovery']['enabled']:
            self.tasks.append(asyncio.create_task(self.parameter_discovery_loop()))
        
        if process_config['model_trainer']['enabled']:
            self.tasks.append(asyncio.create_task(self.model_trainer_loop()))
        
        if process_config['prediction_validator']['enabled']:
            self.tasks.append(asyncio.create_task(self.prediction_validator_loop()))
        
        if process_config['weight_adjuster']['enabled']:
            self.tasks.append(asyncio.create_task(self.weight_adjuster_loop()))
        
        if process_config['optimization_experimenter']['enabled']:
            self.tasks.append(asyncio.create_task(self.optimization_experimenter_loop()))
        
        if process_config['model_selector']['enabled']:
            self.tasks.append(asyncio.create_task(self.model_selector_loop()))
        
        # Always run cleanup and health monitor
        self.tasks.append(asyncio.create_task(self.cleanup_loop()))
        self.tasks.append(asyncio.create_task(self.health_monitor_loop()))
        
        logger.info(f"Started {len(self.tasks)} background processes")
    
    async def stop_all_processes(self):
        """Gracefully stop all processes"""
        logger.info("Stopping all background processes...")
        
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("All background processes stopped")
    
    async def run(self):
        """Main run loop"""
        try:
            self.start_all_processes()
            
            # Run forever (until interrupted)
            while self.running:
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("Received cancellation signal")
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.stop_all_processes()


async def main():
    """Entry point for background system"""
    manager = BackgroundProcessManager()
    
    # Setup signal handlers for graceful shutdown
    try:
        loop = asyncio.get_running_loop()
        
        def signal_handler():
            logger.info("Received shutdown signal")
            asyncio.create_task(manager.stop_all_processes())
        
        # Register signal handlers (Unix/Linux only)
        if hasattr(signal, 'SIGTERM'):
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, signal_handler)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        logger.info("Signal handlers not available (Windows)")
    
    # Run the manager
    await manager.run()


if __name__ == '__main__':
    """
    Run this script to start all background ML processes
    
    Usage:
        python background_process_manager.py
    
    The system will run silently in background and:
    - Collect data every minute
    - Discover parameters every 6 hours
    - Train models every 12 hours
    - Validate predictions daily
    - Adjust weights daily
    - Select best models weekly
    - Clean up old data daily
    
    All operations are async and non-blocking!
    """
    
    print("=" * 80)
    print("🤖 ML BACKGROUND LEARNING SYSTEM")
    print("=" * 80)
    print()
    print("Starting all background processes...")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutdown complete. Goodbye!")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)
