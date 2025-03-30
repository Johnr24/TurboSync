#!/usr/bin/env python3
"""
Debug script for macOS system tray (menubar) issues.
This script runs several tests to diagnose potential problems with
system tray/menubar integration in TurboSync.
"""

import os
import sys
import subprocess
import tempfile
import logging
import traceback
import platform
import time

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def log_system_info():
    """Log detailed system information"""
    logging.info("===== System Information =====")
    logging.info(f"Platform: {platform.platform()}")
    logging.info(f"OS: {platform.system()} {platform.release()}")
    logging.info(f"OS Version: {platform.version()}")
    logging.info(f"Python: {sys.version}")
    logging.info(f"Executable: {sys.executable}")
    logging.info(f"Working Directory: {os.getcwd()}")
    
    # Check if running in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        logging.info("Running in a virtual environment")
        logging.info(f"Base prefix: {getattr(sys, 'base_prefix', 'N/A')}")
        logging.info(f"Prefix: {sys.prefix}")
    else:
        logging.info("Not running in a virtual environment")

def check_permissions():
    """Check permissions that might affect system tray functionality"""
    logging.info("===== Checking Permissions =====")
    
    # Check if script is being run with sudo
    if os.geteuid() == 0:
        logging.warning("Script is running as root/sudo - this may cause issues with system tray")
    else:
        logging.info("Script is not running as root/sudo")
    
    # Check if we can access system tray related directories
    directories_to_check = [
        '/System/Library/Frameworks/AppKit.framework',
        os.path.expanduser('~/Library/Application Support'),
        os.path.expanduser('~/Library/Caches')
    ]
    
    for directory in directories_to_check:
        if os.path.exists(directory):
            logging.info(f"Directory exists: {directory}")
            if os.access(directory, os.R_OK):
                logging.info(f"  Has read permission")
            else:
                logging.warning(f"  No read permission")
        else:
            logging.warning(f"Directory doesn't exist: {directory}")

def check_dependencies():
    """Check Python dependencies that might affect system tray functionality"""
    logging.info("===== Checking Dependencies =====")
    
    # Check for rumps
    try:
        import rumps
        logging.info(f"rumps version: {getattr(rumps, '__version__', 'Unknown')}")
        logging.info(f"rumps path: {rumps.__file__}")
    except ImportError as e:
        logging.error(f"rumps import error: {e}")
    
    # Check for PyObjC
    try:
        import objc
        import Foundation
        import AppKit
        logging.info(f"PyObjC version: {getattr(objc, '__version__', 'Unknown')}")
        logging.info(f"PyObjC path: {objc.__file__}")
        logging.info(f"Foundation available: {hasattr(Foundation, 'NSObject')}")
        logging.info(f"AppKit available: {hasattr(AppKit, 'NSStatusBar')}")
        
        # Check specific NSStatusBar functionality
        try:
            statusbar = AppKit.NSStatusBar.systemStatusBar()
            logging.info("Successfully accessed system status bar via AppKit")
        except Exception as e:
            logging.error(f"Error accessing system status bar: {e}")
    
    except ImportError as e:
        logging.error(f"PyObjC import error: {e}")

def create_test_icon():
    """Create a test icon file and return its path"""
    temp_dir = tempfile.gettempdir()
    icon_path = os.path.join(temp_dir, "test_icon.png")
    
    try:
        # Try to create a simple icon using PIL
        from PIL import Image, ImageDraw
        
        # Create a 128x128 transparent image
        img = Image.new('RGBA', (128, 128), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw a simple shape
        draw.rectangle([(20, 20), (108, 108)], fill=(255, 0, 0))
        draw.ellipse([(30, 30), (98, 98)], fill=(0, 0, 255))
        
        img.save(icon_path)
        logging.info(f"Created test icon at: {icon_path}")
        return icon_path
    
    except ImportError:
        logging.warning("PIL not available, can't create test icon")
        return None

def test_simple_tray():
    """Test a very simple system tray app with minimal dependencies"""
    logging.info("===== Testing Simple System Tray =====")
    
    # Create a temporary Python script
    fd, script_path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    
    icon_path = create_test_icon()
    
    # Write a minimal system tray app
    with open(script_path, 'w') as f:
        f.write("""
import os
import sys
import time
import rumps

class SimpleApp(rumps.App):
    def __init__(self):
        print("Initializing simple app")
        super(SimpleApp, self).__init__(
            "Simple",
            icon={icon}
        )
        print("App initialized")
        self.menu = ["Test", "Quit"]
    
    @rumps.clicked("Test")
    def test(self, _):
        print("Test clicked")
        rumps.notification("Simple", "Test", "This is a test", sound=True)
    
    @rumps.clicked("Quit")
    def quit(self, _):
        print("Quitting")
        rumps.quit_application()

if __name__ == "__main__":
    print("Starting simple app")
    app = SimpleApp()
    print("Running app")
    app.run()
    print("App exited")
""".format(icon=repr(icon_path) if icon_path else 'None'))
    
    # Run the script in a separate process
    logging.info(f"Running test script: {script_path}")
    try:
        # Start process and return immediately 
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for a few seconds to let the app initialize
        logging.info("Waiting for app to initialize...")
        time.sleep(5)
        
        # Check if process is still running
        if process.poll() is None:
            logging.info("Test app is running successfully")
            
            # Kill the process
            process.terminate()
            process.wait(timeout=2)
            logging.info("Test app terminated")
        else:
            # Process already exited
            stdout, stderr = process.communicate()
            logging.error(f"Test app exited prematurely with code {process.returncode}")
            logging.error(f"STDOUT: {stdout}")
            logging.error(f"STDERR: {stderr}")
        
    except Exception as e:
        logging.error(f"Error running test script: {e}")
        traceback.print_exc()
    
    # Clean up
    try:
        os.unlink(script_path)
        if icon_path and os.path.exists(icon_path):
            os.unlink(icon_path)
    except Exception as e:
        logging.error(f"Error cleaning up: {e}")

def test_turbosync_tray():
    """Test TurboSync's tray functionality directly"""
    logging.info("===== Testing TurboSync Tray =====")
    
    try:
        # Import and run the test_tray.py script
        import test_tray
        logging.info("Imported test_tray.py successfully")
        
        # Run in a separate process to avoid blocking
        logging.info("Starting test_tray.py in a separate process")
        process = subprocess.Popen(
            [sys.executable, "test_tray.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for a few seconds
        logging.info("Waiting for test_tray.py to initialize...")
        time.sleep(5)
        
        # Check if process is still running
        if process.poll() is None:
            logging.info("test_tray.py is running successfully")
            
            # Kill the process
            process.terminate()
            process.wait(timeout=2)
            logging.info("test_tray.py terminated")
        else:
            # Process already exited
            stdout, stderr = process.communicate()
            logging.error(f"test_tray.py exited prematurely with code {process.returncode}")
            logging.error(f"STDOUT: {stdout}")
            logging.error(f"STDERR: {stderr}")
        
    except Exception as e:
        logging.error(f"Error testing TurboSync tray: {e}")
        traceback.print_exc()

def main():
    logging.info("===== Starting System Tray Debug =====")
    
    # Run tests
    log_system_info()
    check_permissions()
    check_dependencies()
    test_simple_tray()
    test_turbosync_tray()
    
    logging.info("===== System Tray Debug Complete =====")

if __name__ == "__main__":
    main() 