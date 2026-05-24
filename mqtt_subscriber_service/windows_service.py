"""
Windows Service Wrapper for MQTT Subscriber Service
Uses pywin32 to run the service as a Windows Service
"""

import sys
import os
import time
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
from pathlib import Path

# Add src to path
service_root = str(Path(__file__).parent)
sys.path.insert(0, service_root)

# Don't import service_main here - do it inside main() to catch errors
logger = None  # Will be set later


class MQTTSubscriberWindowsService(win32serviceutil.ServiceFramework):
    """Windows Service wrapper for MQTT Subscriber"""
    
    _svc_name_ = "MQTTSubscriberService"
    _svc_display_name_ = "MQTT Subscriber Service"
    _svc_description_ = "Enterprise MQTT data subscriber service that processes industrial IoT data and stores to PostgreSQL historian database"
    
    def __init__(self, args):
        """Initialize the service"""
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_alive = True
        self.service = None
    
    def SvcStop(self):
        """Called when the service is requested to stop"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        
        if logger:
            logger.info("Windows Service stop requested")
        
        # Signal stop event first
        self.is_alive = False
        win32event.SetEvent(self.stop_event)
        
        # Stop the MQTT service gracefully with timeout
        if self.service:
            try:
                # Call stop() method which sets running=False and calls shutdown()
                self.service.stop()
                time.sleep(1)  # Give it time to finish
            except Exception as e:
                if logger:
                    logger.error(f"Error stopping service: {e}")
        
        # Final report
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)
    
    def SvcDoRun(self):
        """Called when the service is started"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        # Don't use logger here - it's not initialized yet
        self.main()
    
    def main(self):
        """Main service loop"""
        service_started = False
        debug_log = None
        
        try:
            # Create emergency debug log file
            debug_log_path = os.path.join(os.path.dirname(__file__), 'logs', 'service_debug.txt')
            os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
            debug_log = open(debug_log_path, 'a')
            debug_log.write(f"\n{'='*60}\n")
            debug_log.write(f"Service Start Attempt: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            debug_log.flush()
            
            # Import service classes
            debug_log.write("Step 1: Importing service classes...\n")
            debug_log.flush()
            
            from src.service_main import MQTTSubscriberService
            debug_log.write("Step 1a: MQTTSubscriberService imported\n")
            debug_log.flush()
            
            from src.monitoring.logger import get_logger
            debug_log.write("Step 1b: get_logger imported\n")
            debug_log.flush()
            
            global logger
            logger = get_logger(__name__)
            debug_log.write("Step 1c: logger initialized\n")
            debug_log.flush()
            
            debug_log.write("Step 2: Imports successful\n")
            debug_log.flush()
            
            # Skip servicemanager calls - they seem to crash the service
            debug_log.write("Step 3: Skipping servicemanager calls\n")
            debug_log.flush()
            
            # Initialize service
            config_path = os.path.join(
                os.path.dirname(__file__),
                'config',
                'service_config.yaml'
            )
            
            debug_log.write(f"Step 4: Config path: {config_path}\n")
            debug_log.write(f"Step 5: Config exists: {os.path.exists(config_path)}\n")
            debug_log.flush()
            
            debug_log.write("Step 6a: About to create MQTTSubscriberService object\n")
            debug_log.flush()
            
            try:
                self.service = MQTTSubscriberService(config_path)
                debug_log.write("Step 6b: MQTTSubscriberService object created successfully\n")
                debug_log.flush()
            except Exception as e:
                import traceback
                debug_log.write(f"Step 6b ERROR: Failed to create service object: {e}\n")
                debug_log.write(f"Traceback:\n{traceback.format_exc()}\n")
                debug_log.flush()
                raise
            
            debug_log.write("Step 6: Service object created\n")
            debug_log.flush()
            
            # Removed servicemanager call - causes crash
            
            debug_log.write("Step 7a: Calling service.initialize()\n")
            debug_log.flush()
            
            try:
                self.service.initialize()
                debug_log.write("Step 7b: service.initialize() completed successfully\n")
                debug_log.flush()
            except Exception as e:
                import traceback
                debug_log.write(f"Step 7b ERROR: service.initialize() failed: {e}\n")
                debug_log.write(f"Traceback:\n{traceback.format_exc()}\n")
                debug_log.flush()
                raise
            
            debug_log.write("Step 7: Service initialized\n")
            debug_log.flush()
            
            # Removed servicemanager call - causes crash
            logger.info("MQTT Subscriber Service initialized")
            
            # Start the service
            debug_log.write("Step 8: Starting service main loop\n")
            debug_log.flush()
            
            # Removed servicemanager call - causes crash
            service_started = True
            
            # Run service in non-blocking mode
            import threading
            service_thread = threading.Thread(target=self.service.start, daemon=True)
            service_thread.start()
            
            # Wait for stop event with shorter intervals for faster response
            while self.is_alive:
                result = win32event.WaitForSingleObject(self.stop_event, 500)  # 500ms timeout
                if result == win32event.WAIT_OBJECT_0:
                    # Stop event was signaled
                    break
            
            # Wait for service thread to finish (with timeout)
            service_thread.join(timeout=5)
            
            logger.info("Windows Service stopped")
            # Removed servicemanager call - causes crash
            
        except Exception as e:
            error_msg = f"Service failed: {str(e)}"
            if debug_log:
                import traceback
                debug_log.write(f"ERROR: {error_msg}\n")
                debug_log.write(f"Traceback:\n{traceback.format_exc()}\n")
                debug_log.flush()
            
            if service_started and logger:
                logger.error(error_msg, exc_info=True)
            # Removed servicemanager call - causes crash
            # Re-raise to let Windows know the service failed
            raise
        finally:
            if debug_log:
                debug_log.write(f"Service stopped at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                debug_log.close()


def main():
    """Main entry point for service installation"""
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(MQTTSubscriberWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(MQTTSubscriberWindowsService)


if __name__ == '__main__':
    main()
