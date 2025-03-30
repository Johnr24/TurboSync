import os
import sys
import logging
import subprocess
from dotenv import load_dotenv
import multiprocessing

# Suppress the RuntimeWarning messages about module imports
# This doesn't fix the underlying issue but stops the warnings from appearing
os.environ["PYTHONWARNINGS"] = "ignore::RuntimeWarning"

# Setup multiprocessing before importing any other modules
# This prevents the "found in sys.modules" warnings
if __name__ == "__main__" or not "pytest" in sys.modules:
    multiprocessing.freeze_support()
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        # Already set or not available, ignore
        pass

# Import these after multiprocessing is configured
from .menubar import run_app
from .watcher import is_fswatch_available, get_fswatch_config
import threading

def setup_logging():
    """Set up enhanced logging with console output for debugging"""
    # Set up logging directory
    log_dir = os.path.expanduser('~/Library/Logs/TurboSync')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'turbosync.log')
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Set to DEBUG level for more detailed logs
    
    # File handler for detailed logs
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)
    
    # Console handler for immediate feedback during debugging
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    logging.info("===== TurboSync Starting =====")
    logging.info(f"Python version: {sys.version}")
    logging.info(f"Running from: {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")
    logging.info(f"Log file: {log_file}")
    
    # Log system information
    try:
        import platform
        logging.info(f"Platform: {platform.platform()}")
        logging.info(f"OS: {platform.system()} {platform.release()}")
    except Exception as e:
        logging.error(f"Failed to get platform info: {e}")
    
    return log_file

def ensure_env_file():
    """Ensure the .env file exists, create it if it doesn't"""
    logging.debug("Checking for .env file")
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(script_dir, ".env")
    
    if not os.path.exists(env_path):
        logging.info(f".env file not found at {env_path}, creating default")
        # Copy the template .env file or create a new one
        template_content = """# Remote server configuration
REMOTE_USER=username
REMOTE_HOST=example.com
REMOTE_PORT=22
REMOTE_DIR=/path/to/remote/directory

# Use mounted volume instead of SSH (if volume is mounted in Finder)
USE_MOUNTED_VOLUME=false
# Direct path to mounted volume in Finder (leave empty if not using mounted volume)
MOUNTED_VOLUME_PATH=

# Local directory to sync to
LOCAL_DIR=/path/to/local/directory

# Sync interval in minutes
SYNC_INTERVAL=5

# Watch local files for changes
WATCH_LOCAL_FILES=true
WATCH_DELAY_SECONDS=2

# Rclone options - optimized for performance
RCLONE_OPTIONS=--progress --transfers=4 --checkers=8 --buffer-size=32M --fast-list --delete-excluded --exclude=".*" --exclude="node_modules"

# Parallel sync (multiple connections)
ENABLE_PARALLEL_SYNC=true
PARALLEL_PROCESSES=4
"""
        with open(env_path, 'w') as f:
            f.write(template_content)
        
        logging.info(f"Created default .env file at {env_path}")
        
        # Open the .env file for editing
        os.system(f"open {env_path}")
        
        # Show message to user
        import rumps
        rumps.notification(
            "TurboSync Setup",
            "Configuration Required",
            "Please edit the .env file with your settings before starting TurboSync.",
            sound=True
        )
        return False
    
    logging.debug(f".env file found at {env_path}")
    return True

def setup_icon():
    """Create a simple app icon if it doesn't exist"""
    logging.debug("Setting up application icon")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(script_dir, "icon.png")
    
    # List of additional possible icon locations
    possible_icon_paths = []
    
    # Add additional icon paths for PyInstaller environment
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller's temp folder during execution
        logging.debug(f"Running in PyInstaller environment, MEIPASS: {sys._MEIPASS}")
        possible_icon_paths.extend([
            os.path.join(sys._MEIPASS, "icon.png"),
            os.path.join(sys._MEIPASS, "turbo_sync", "icon.png"),
            os.path.join(os.path.dirname(sys.executable), "..", "Resources", "icon.png"),
            os.path.join(os.path.dirname(sys.executable), "icon.png")
        ])
    
    # Add other possible locations
    executable_dir = os.path.dirname(sys.executable)
    possible_icon_paths.extend([
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "turbo_sync", "icon.png"),
        os.path.join(executable_dir, "..", "Resources", "icon.png"),
        "/Applications/TurboSync.app/Contents/Resources/icon.png"
    ])

    # First check if icon exists in any of the possible paths
    for path in possible_icon_paths:
        if path and os.path.exists(path):
            logging.info(f"Found icon at: {path}")
            try:
                # Copy to the expected location
                with open(path, 'rb') as src_file:
                    os.makedirs(os.path.dirname(icon_path), exist_ok=True)
                    with open(icon_path, 'wb') as dst_file:
                        data = src_file.read()
                        dst_file.write(data)
                logging.info(f"Copied icon from {path} to {icon_path}")
                return
            except Exception as e:
                logging.error(f"Error copying icon: {e}")
    
    # If icon doesn't exist at the main location, create it
    if not os.path.exists(icon_path):
        logging.info(f"Icon not found at {icon_path}, attempting to create")
        try:
            # Create a simple icon using PIL if available
            from PIL import Image, ImageDraw
            
            # Create a 128x128 transparent image
            img = Image.new('RGBA', (128, 128), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # First create a RGB flag background
            rainbow_colors = [
                (228, 3, 3),    # Red
                (255, 140, 0),  # Orange
                (255, 237, 0),  # Yellow
                (0, 128, 38),   # Green
                (0, 77, 255),   # Blue
                (117, 7, 135)   # Purple
            ]
            
            # Draw rainbow stripes
            stripe_height = 128 // len(rainbow_colors)
            for i, color in enumerate(rainbow_colors):
                y1 = i * stripe_height
                y2 = y1 + stripe_height
                draw.rectangle([(0, y1), (128, y2)], fill=color)
            
            # Draw a white "T" for TurboSync
            draw.rectangle([(50, 20), (78, 108)], fill=(255, 255, 255))
            draw.rectangle([(30, 20), (98, 40)], fill=(255, 255, 255))
            
            os.makedirs(os.path.dirname(icon_path), exist_ok=True)
            img.save(icon_path)
            logging.info(f"Created icon at {icon_path}")
            
            # Also save a copy to a well-known location for the menubar app to find
            temp_dir = os.path.expanduser("~/Library/Logs/TurboSync")
            os.makedirs(temp_dir, exist_ok=True)
            temp_icon_path = os.path.join(temp_dir, "icon.png")
            img.save(temp_icon_path)
            logging.info(f"Saved backup icon to {temp_icon_path}")
            
        except ImportError:
            # If PIL is not available, we'll just use a default icon from the system
            logging.warning("PIL not available, using default icon")
            
            # Create an empty file as placeholder
            os.makedirs(os.path.dirname(icon_path), exist_ok=True)
            with open(icon_path, 'wb') as f:
                f.write(b'')
    else:
        logging.debug(f"Icon already exists at {icon_path}")
        
    # Make sure we copy the icon to a well-known location for the menubar to find
    try:
        if os.path.exists(icon_path) and os.path.getsize(icon_path) > 0:
            temp_dir = os.path.expanduser("~/Library/Logs/TurboSync")
            os.makedirs(temp_dir, exist_ok=True)
            temp_icon_path = os.path.join(temp_dir, "icon.png")
            with open(icon_path, 'rb') as src:
                with open(temp_icon_path, 'wb') as dst:
                    dst.write(src.read())
            logging.debug(f"Copied icon to well-known location: {temp_icon_path}")
    except Exception as e:
        logging.error(f"Error copying icon to well-known location: {e}")

def check_dependencies():
    """Check if required external dependencies are available"""
    logging.debug("Checking dependencies")
    # Check if rclone is available
    try:
        result = subprocess.run(["rclone", "version"], capture_output=True, check=True)
        rclone_version = result.stdout.decode('utf-8').split('\n')[0]
        logging.info(f"rclone found: {rclone_version}")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logging.error(f"rclone not found: {e}")
        import rumps
        rumps.notification(
            "TurboSync Error",
            "rclone Not Found",
            "rclone is required for TurboSync to work. Please install it with: brew install rclone",
            sound=True
        )
        logging.error("rclone not found - required for TurboSync to work")
        return False
    
    # Check if fswatch is available if file watching is enabled
    fswatch_config = get_fswatch_config()
    if fswatch_config['watch_enabled']:
        if is_fswatch_available():
            try:
                result = subprocess.run(["fswatch", "--version"], capture_output=True, check=True)
                fswatch_version = result.stdout.decode('utf-8').strip()
                logging.info(f"fswatch found: {fswatch_version}")
            except Exception as e:
                logging.warning(f"Error getting fswatch version: {e}")
        else:
            logging.warning("fswatch not found - file watching will be disabled")
            import rumps
            rumps.notification(
                "TurboSync Warning",
                "fswatch Not Found",
                "File watching is enabled but fswatch is not installed. Install with: brew install fswatch",
                sound=True
            )
    
    return True

def main():
    """Main entry point for the application"""
    try:
        # Set up logging
        log_file = setup_logging()
        
        try:
            # Log startup information
            logging.info("TurboSync main function started")
            
            # Create icon
            setup_icon()
            
            # Ensure app is set to be agent app on macOS
            ensure_app_is_agent()
            
            # Ensure .env file exists
            if not ensure_env_file():
                logging.warning("Setup incomplete - .env file needs configuration")
                return
            
            # Load environment variables
            load_dotenv()
            logging.debug("Environment variables loaded")
            
            # Check dependencies
            if not check_dependencies():
                logging.error("Dependencies check failed")
                return
            
            # Start the app
            logging.info("Starting main application")
            if threading.current_thread() is threading.main_thread():
                run_app()
            else:
                logging.error("TurboSync must be run from the main thread")
                print("Error: TurboSync must be run from the main thread")
                sys.exit(1)
        except Exception as e:
            logging.exception(f"Unexpected error in main function: {e}")
            import rumps
            rumps.notification(
                "TurboSync Error",
                "Application Error",
                f"An unexpected error occurred: {str(e)}. Check logs at {log_file}",
                sound=True
            )
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)

def ensure_app_is_agent():
    """Make sure the macOS app is properly set as a menubar/agent app"""
    if sys.platform != 'darwin':
        logging.debug("Not running on macOS, skipping agent app check")
        return
    
    # Only needs to be done for the bundled app
    if not hasattr(sys, '_MEIPASS'):
        logging.debug("Not running as a bundled app, skipping agent app check")
        return
    
    logging.debug("Checking if app is properly set as an agent app")
    
    try:
        # First determine if we're running from a .app bundle
        executable_path = os.path.abspath(sys.executable)
        if ".app/Contents/MacOS/" not in executable_path:
            logging.debug("Not running from a .app bundle, skipping agent app check")
            return
            
        # Get the path to the app bundle's Info.plist
        app_bundle_path = executable_path.split(".app/Contents/MacOS/")[0] + ".app"
        plist_path = os.path.join(app_bundle_path, "Contents", "Info.plist")
        
        if not os.path.exists(plist_path):
            logging.warning(f"Info.plist not found at {plist_path}, cannot update app type")
            return
            
        logging.info(f"App is running from bundle: {app_bundle_path}")
        logging.debug(f"Info.plist path: {plist_path}")
        
        # Check if LSUIElement is already set
        import plistlib
        with open(plist_path, 'rb') as f:
            plist = plistlib.load(f)
            
        if 'LSUIElement' in plist and plist['LSUIElement'] is True:
            logging.debug("App is already properly set as an agent app (LSUIElement=True)")
            return
            
        # Set LSUIElement to True to make it a menubar app
        logging.info("Setting app as menubar/agent app (LSUIElement=True)")
        plist['LSUIElement'] = True
        
        # Write the updated plist
        try:
            # The app bundle might be in a location where we can't write
            # So we'll use a temp file and then try to use sudo if needed
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as temp:
                temp_path = temp.name
                with open(temp_path, 'wb') as f:
                    plistlib.dump(plist, f)
                
            # Try to copy the temp file to the plist location
            import shutil
            try:
                shutil.copy2(temp_path, plist_path)
                logging.info(f"Updated Info.plist at {plist_path}")
            except PermissionError:
                # If we don't have permission, try with sudo
                logging.warning("Permission denied, trying with sudo")
                import subprocess
                subprocess.run(['sudo', 'cp', temp_path, plist_path], check=True)
                logging.info(f"Updated Info.plist at {plist_path} using sudo")
                
            # Clean up temp file
            os.unlink(temp_path)
        except Exception as e:
            logging.error(f"Failed to update Info.plist: {e}")
    except Exception as e:
        logging.error(f"Error ensuring app is agent app: {e}")

if __name__ == "__main__":
    main()
