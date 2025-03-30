#!/usr/bin/env python3
"""
Simple test script for menubar/tray icon
"""

import os
import sys
import time
import logging
import threading
import rumps

# Set up enhanced logging
def setup_logging():
    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info("Logging initialized for tray test")

def check_rumps():
    # Get rumps version and info
    logging.info(f"Rumps version: {rumps.__version__ if hasattr(rumps, '__version__') else 'unknown'}")
    logging.info(f"Rumps path: {rumps.__file__}")
    
    # Check if PyObjC is available and get version
    try:
        import objc
        logging.info(f"PyObjC version: {objc.__version__ if hasattr(objc, '__version__') else 'unknown'}")
        logging.info(f"PyObjC path: {objc.__file__}")
    except ImportError:
        logging.warning("PyObjC not available")

class TestApp(rumps.App):
    def __init__(self):
        logging.info("Initializing test app")
        
        # Find icon path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "turbo_sync", "icon.png")
        
        logging.info(f"Icon path: {icon_path}")
        logging.info(f"Icon exists: {os.path.exists(icon_path)}")
        
        try:
            logging.info("Creating rumps.App instance")
            super(TestApp, self).__init__(
                "Test App",
                icon=icon_path if os.path.exists(icon_path) else None
            )
            logging.info("Rumps app initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing rumps app: {e}", exc_info=True)
            # Try again without icon
            super(TestApp, self).__init__("Test App")
            logging.info("Initialized rumps.App without icon")
        
        # Set up menu items
        self.menu = ["Test Action", None, "Quit"]
        logging.info("Menu items created")
    
    @rumps.clicked("Test Action")
    def test_action(self, _):
        logging.info("Test action clicked")
        rumps.notification(
            "Test App",
            "Notification Test",
            "This is a test notification",
            sound=True
        )
    
    @rumps.clicked("Quit")
    def quit_app(self, _):
        logging.info("Quit clicked")
        rumps.quit_application()

def main():
    setup_logging()
    logging.info("===== Test Tray App Starting =====")
    
    # Log system information
    try:
        import platform
        logging.info(f"Platform: {platform.platform()}")
        logging.info(f"OS: {platform.system()} {platform.release()}")
        logging.info(f"Python version: {sys.version}")
    except Exception as e:
        logging.error(f"Failed to get platform info: {e}")
    
    # Check rumps installation
    check_rumps()
    
    try:
        # Create and run the app
        logging.info("Creating TestApp instance")
        app = TestApp()
        
        # Run the app - this call blocks until the app quits
        logging.info("Starting rumps application")
        app.run()
        logging.info("rumps application has exited")
    except Exception as e:
        logging.exception(f"Error in test app: {e}")

if __name__ == "__main__":
    main() 