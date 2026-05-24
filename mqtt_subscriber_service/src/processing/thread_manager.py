"""
Thread Pool Manager
Manages worker threads for message processing
"""

import queue
import threading
from typing import Callable
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class ThreadPoolManager:
    """Thread pool for processing MQTT messages"""
    
    def __init__(self, num_workers: int, task_queue_size: int = 1000):
        """
        Initialize Thread Pool Manager
        
        Args:
            num_workers: Number of worker threads
            task_queue_size: Maximum queue size
        """
        self.num_workers = num_workers
        self.task_queue = queue.Queue(maxsize=task_queue_size)
        self.workers = []
        self.running = False
        
        # Statistics
        self.stats = {
            'tasks_submitted': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'queue_full_count': 0
        }
        
        logger.info(f"ThreadPoolManager initialized with {num_workers} workers")
    
    def start(self, task_processor: Callable):
        """
        Start worker threads
        
        Args:
            task_processor: Function to process tasks (callable)
        """
        if self.running:
            logger.warning("ThreadPoolManager already running")
            return
        
        self.running = True
        
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(task_processor,),
                name=f"Worker-{i+1}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
        
        logger.info(f"Started {len(self.workers)} worker threads")
    
    def _worker_loop(self, task_processor: Callable):
        """
        Worker thread loop
        
        Args:
            task_processor: Function to process tasks
        """
        thread_name = threading.current_thread().name
        logger.debug(f"{thread_name} started")
        
        while self.running:
            try:
                # Get task from queue with timeout
                task = self.task_queue.get(timeout=1)
                
                if task is None:  # Poison pill to stop worker
                    break
                
                # Process task
                try:
                    task_processor(task)
                    self.stats['tasks_completed'] += 1
                except Exception as e:
                    logger.error(f"{thread_name} - Task processing failed: {e}")
                    self.stats['tasks_failed'] += 1
                finally:
                    self.task_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"{thread_name} - Worker error: {e}")
        
        logger.debug(f"{thread_name} stopped")
    
    def submit_task(self, task) -> bool:
        """
        Submit task to queue
        
        Args:
            task: Task object to process
            
        Returns:
            True if submitted, False if queue full
        """
        try:
            self.task_queue.put(task, block=False)
            self.stats['tasks_submitted'] += 1
            return True
        except queue.Full:
            logger.warning("Task queue is full, dropping task")
            self.stats['queue_full_count'] += 1
            return False
    
    def stop(self, wait: bool = True):
        """
        Stop worker threads
        
        Args:
            wait: Wait for workers to finish
        """
        if not self.running:
            return
        
        logger.info("Stopping ThreadPoolManager...")
        self.running = False
        
        # Send poison pills to stop workers
        for _ in range(self.num_workers):
            self.task_queue.put(None)
        
        if wait:
            for worker in self.workers:
                worker.join(timeout=5)
        
        self.workers.clear()
        logger.info("ThreadPoolManager stopped")
    
    def get_stats(self) -> dict:
        """Get thread pool statistics"""
        return {
            **self.stats,
            'num_workers': self.num_workers,
            'queue_size': self.task_queue.qsize(),
            'is_running': self.running
        }
