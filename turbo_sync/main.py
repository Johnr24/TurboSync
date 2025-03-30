.................import os
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
from turbo_sync.menubar import run_app
from turbo_sync.watcher import is_fswatch_available, get_fswatch_config # Changed to absolute import
from turbo_sync.utils import get_resource_path # Import from utils
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

# Removed get_resource_path function (moved to utils.py)

def ensure_env_file():
    """Ensure the .env file exists, create it if it doesn't"""
    logging.debug("Checking for .env file")
    env_path = get_resource_path(".env")
    
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
    """Ensure the icon file path is correctly determined for the menubar app."""
    logging.debug("Determining application icon path")
    # The icon is bundled by PyInstaller. We just need to provide the path.
    # The menubar library (rumps) expects the icon name relative to resources.
    # PyInstaller puts data files in the root of the bundle or sys._MEIPASS.
    # The build script includes 'icon.png' in the 'datas' list.
    icon_path = get_resource_path("icon.png")
    
    if os.path.exists(icon_path):
        logging.info(f"Icon found at expected bundled location: {icon_path}")
        # rumps typically handles finding the icon if named correctly and bundled,
        # but we return the path for potential direct use if needed elsewhere.
        return icon_path 
    else:
        # This case should ideally not happen if the build script is correct.
        logging.error(f"Bundled icon not found at expected path: {icon_path}")
        # Fallback: Try the original source location (might work in dev)
        source_icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(source_icon_path):
             logging.warning(f"Falling back to source icon path: {source_icon_path}")
             return source_icon_path
        else:
             logging.error("Icon file 'icon.png' is missing from bundle and source location.")
             return None # Indicate icon is missing

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
            # Get icon path (setup_icon now just returns the path)
            icon_path = setup_icon() 
            # Note: The actual icon setting is handled within run_app (menubar.py)
            
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

# Removed ensure_app_is_agent() function as it's handled by PyInstaller build

if __name__ == "__main__":
    main()
