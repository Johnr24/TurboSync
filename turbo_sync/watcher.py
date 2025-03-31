import os
import time
import logging
import threading
import subprocess
import shutil # Added for shutil.which fallback
# from fswatch import Monitor # Removed - Using subprocess directly
from dotenv import load_dotenv

# Use the root logger instead of a custom one to keep logging consistent
# logger = logging.getLogger('TurboSync')

class FileWatcher:
    def __init__(self, local_dir, callback, delay_seconds=2):
        """
        Initialize a file watcher for the specified directory
        
        Args:
            local_dir: Directory to watch
            callback: Function to call when changes are detected
            delay_seconds: Debounce delay to avoid multiple callbacks
        """
        logging.info(f"Initializing FileWatcher for {local_dir} with {delay_seconds}s delay")
        self.local_dir = os.path.expanduser(local_dir)
        self.callback = callback
        self.delay_seconds = delay_seconds
        # self.monitor = None # Removed - Using subprocess directly
        self.watcher_thread = None
        self.running = False
        self.last_event_time = 0
        self._lock = threading.Lock()
        self.event_count = 0
        
        # Ensure the directory exists
        if not os.path.exists(self.local_dir):
            logging.info(f"Creating local directory: {self.local_dir}")
            os.makedirs(self.local_dir, exist_ok=True)
            logging.info(f"Created local directory: {self.local_dir}")
        else:
            logging.debug(f"Local directory already exists: {self.local_dir}")
            
        # Log initial directory contents
        try:
            logging.info(f"Initial directory contents of {self.local_dir}:")
            for root, dirs, files in os.walk(self.local_dir):
                level = root.replace(self.local_dir, '').count(os.sep)
                indent = ' ' * 4 * level
                logging.info(f"{indent}{os.path.basename(root)}/")
                subindent = ' ' * 4 * (level + 1)
                for f in files:
                    logging.info(f"{subindent}{f}")
        except Exception as e:
            logging.error(f"Error listing initial directory contents: {e}")
    
    def _handle_event(self, path):
        """Handle a file system event with debouncing"""
        current_time = time.time()
        self.event_count += 1
        
        with self._lock:
            # Log detailed event information
            try:
                event_type = "Directory" if os.path.isdir(path) else "File"
                event_size = os.path.getsize(path) if os.path.isfile(path) else "N/A"
                event_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(path)))
                logging.info(f"File System Event #{self.event_count}:")
                logging.info(f"  Path: {path}")
                logging.info(f"  Type: {event_type}")
                logging.info(f"  Size: {event_size}")
                logging.info(f"  Modified: {event_time}")
            except Exception as e:
                logging.error(f"Error getting event details: {e}")
            
            # Debounce - only trigger if it's been longer than delay_seconds since the last event
            if current_time - self.last_event_time > self.delay_seconds:
                logging.info(f"Change detected in {path}")
                self.last_event_time = current_time
                
                # Wait a bit for all changes to settle and then call the callback
                # This prevents multiple rapid syncs
                logging.debug(f"Scheduling callback with {self.delay_seconds}s delay")
                threading.Timer(self.delay_seconds, self.callback).start()
            else:
                logging.debug(f"Debounced change event for {path}")
    
    def start(self):
        """Start watching for file changes"""
        if self.running:
            logging.debug("FileWatcher already running")
            return True
        
        try:
            logging.info(f"Starting file watcher for {self.local_dir}")

            # Removed Monitor creation/usage - using subprocess directly
            # logging.debug("Creating fswatch Monitor")
            # self.monitor = Monitor()
            # self.monitor.add_path(self.local_dir)
            # logging.debug(f"Added path to monitor: {self.local_dir}")
            #
            # # Set callback
            # self.monitor.set_callback(self._handle_event)

            # Use alternative file watching approach instead of fswatch Monitor's built-in signal handling
            # This avoids the "signal only works in main thread" error
            logging.debug("Starting file watching through subprocess")
            self.running = True
            self.watcher_thread = threading.Thread(target=self._watch_files_subprocess, daemon=True)
            self.watcher_thread.start()
            
            logging.info("File watcher started successfully")
            return True
        
        except Exception as e:
            logging.error(f"Error starting file watcher: {str(e)}", exc_info=True)
            self.running = False
            return False
    
    def _watch_files_subprocess(self):
        """Watch files using a subprocess to avoid signal handling issues"""
        fswatch_path = _get_bundled_fswatch_path()
        if not fswatch_path:
            logging.error("fswatch executable not found. Cannot start file watcher subprocess.")
            self.running = False
            return

        try:
            logging.debug(f"Starting fswatch subprocess using path: {fswatch_path}")
            process = subprocess.Popen(
                [fswatch_path, "-r", self.local_dir], # Use the determined path
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            logging.info(f"fswatch process started with PID: {process.pid}")
            
            while self.running:
                # Read a line (blocking)
                line = process.stdout.readline().strip()
                if line:
                    self._handle_event(line)
                
                # Check if process is still running
                if process.poll() is not None:
                    if self.running:
                        logging.error("fswatch process died unexpectedly")
                        self.running = False
                    break
                    
            # Clean up
            if process.poll() is None:
                logging.info("Terminating fswatch process")
                process.terminate()
                try:
                    process.wait(timeout=2)
                    logging.info("fswatch process terminated successfully")
                except subprocess.TimeoutExpired:
                    logging.warning("fswatch process did not terminate, forcing kill")
                    process.kill()
                    
            logging.debug("Watcher subprocess terminated")
                
        except Exception as e:
            logging.error(f"Error in file watcher subprocess: {str(e)}", exc_info=True)
            self.running = False

    # Removed unused _watch_files method which used the fswatch Python package Monitor
    # def _watch_files(self):
    #     """
    #     Original implementation using Monitor.start() - not used due to signal issues
    #     Kept for reference
    #     """
    #     try:
    #         logging.debug("Watcher thread started, calling monitor.start()")
    #         self.monitor.start()
    #         logging.debug("Monitor.start() returned")
    #     except Exception as e:
    #         logging.error(f"File watcher error: {str(e)}", exc_info=True)
    #         self.running = False

    def stop(self):
        """Stop watching for file changes"""
        if not self.running:
            logging.debug("FileWatcher not running, nothing to stop")
            return
        
        try:
            logging.info("Stopping file watcher")
            self.running = False

            # Removed monitor reference
            # if self.monitor:
            #     logging.debug("Stopping monitor")
            #     self.monitor = None

            logging.info(f"File watcher stopped. Total events processed: {self.event_count}")
        except Exception as e:
            logging.error(f"Error stopping file watcher: {str(e)}", exc_info=True)


def _get_bundled_fswatch_path():
    """Determines the expected path to the fswatch binary bundled within the app."""
    # When running as a bundled app, sys.executable is inside Contents/MacOS
    # The bundled fswatch should be in the same directory.
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as a PyInstaller bundle
        base_path = os.path.dirname(sys.executable)
        fswatch_path = os.path.join(base_path, 'fswatch')
        logging.debug(f"Checking for bundled fswatch at: {fswatch_path}")
        return fswatch_path
    else:
        # Not running as a bundled app (e.g., running from source)
        # In this case, rely on system PATH using shutil.which
        logging.debug("Not running as a bundled app, checking system PATH for fswatch.")
        return shutil.which("fswatch")

def is_fswatch_available():
    """Check if fswatch is available, prioritizing the bundled version."""
    logging.debug("Checking if fswatch is available (prioritizing bundled)...")
    fswatch_path = _get_bundled_fswatch_path()

    if fswatch_path and os.path.exists(fswatch_path) and os.access(fswatch_path, os.X_OK):
        logging.info(f"fswatch is available and executable at: {fswatch_path}")
        return True
    else:
        logging.warning(f"fswatch not found or not executable at expected path: {fswatch_path}")
        # Optional: Add a fallback check on the system PATH if needed, but the primary
        # expectation is that the bundled version works.
        # system_path = shutil.which("fswatch")
        # if system_path:
        #    logging.warning(f"Bundled fswatch failed, but found on system PATH: {system_path}. Consider issues with bundling.")
        #    # Decide if using system path is acceptable fallback
        return False


def get_fswatch_config():
    """Get fswatch configuration from .env file"""
    logging.debug("Loading fswatch configuration from environment")
    load_dotenv()
    
    watch_enabled = os.getenv('WATCH_LOCAL_FILES', 'true').lower() == 'true'
    watch_delay = int(os.getenv('WATCH_DELAY_SECONDS', '2'))
    local_dir = os.path.expanduser(os.getenv('LOCAL_DIR', '~/Live_Work'))
    
    config = {
        'watch_enabled': watch_enabled,
        'watch_delay': watch_delay,
        'local_dir': local_dir
    }
    
    logging.debug(f"Fswatch config: enabled={watch_enabled}, delay={watch_delay}s, dir={local_dir}")
    return config 