"""
Windows Service Wrapper for Background ML System
Allows system to run as Windows service - fully async
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import asyncio
import sys
import os
from pathlib import Path

# Add ML_System to path
sys.path.insert(0, str(Path(__file__).parent))

from background_process_manager import BackgroundProcessManager


class MLBackgroundService(win32serviceutil.ServiceFramework):
    """
    Windows Service for ML Background Learning System
    Runs completely async without blocking
    """
    
    _svc_name_ = "MLBackgroundLearningSystem"
    _svc_display_name_ = "ML Background Learning System"
    _svc_description_ = "Intelligent ML system that learns turbine optimization silently in background"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.manager = None
        socket.setdefaulttimeout(60)
    
    def SvcStop(self):
        """Stop the service"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        
        # Stop background manager
        if self.manager:
            asyncio.run(self.manager.stop_all_processes())
    
    def SvcDoRun(self):
        """Run the service"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        try:
            self.main()
        except Exception as e:
            servicemanager.LogErrorMsg(f"Service error: {e}")
    
    def main(self):
        """Main service loop - runs async"""
        # Initialize background manager
        self.manager = BackgroundProcessManager()
        
        # Run async event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Start all background processes
            loop.run_until_complete(self.manager.run())
        except Exception as e:
            servicemanager.LogErrorMsg(f"Manager error: {e}")
        finally:
            loop.close()


if __name__ == '__main__':
    """
    Install/Start/Stop service from command line:
    
    Install:
        python ml_background_service.py install
    
    Start:
        python ml_background_service.py start
    
    Stop:
        python ml_background_service.py stop
    
    Remove:
        python ml_background_service.py remove
    
    Debug (run in console):
        python ml_background_service.py debug
    """
    
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(MLBackgroundService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(MLBackgroundService)
