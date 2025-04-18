import os
import sys
import subprocess
import logging
import time
import platform

logger = logging.getLogger(__name__)

# Define user-specific config path (consistent with main.py/menubar.py)
APP_NAME = "TurboSync"
USER_CONFIG_DIR = os.path.expanduser(f'~/Library/Application Support/{APP_NAME}')
SYNCTHING_CONFIG_DIR = os.path.join(USER_CONFIG_DIR, 'syncthing_config')
SYNCTHING_LOG_FILE = os.path.join(os.path.expanduser('~/Library/Logs/TurboSync'), 'syncthing.log')
DEFAULT_SYNCTHING_API_ADDRESS = "127.0.0.1:8385" # Default API address

def get_syncthing_executable_path():
    """Finds the bundled Syncthing binary path."""
    logger.debug("Attempting to find Syncthing executable...")
    if getattr(sys, 'frozen', False):
        # Running as a bundled app (PyInstaller)
        base_path = sys._MEIPASS
        # The binary should be copied to Contents/MacOS alongside the main executable
        # Adjust the relative path if build_app.py places it elsewhere within the bundle
        executable_path = os.path.join(os.path.dirname(sys.executable), 'syncthing')
        logger.debug(f"Running bundled, expecting syncthing at: {executable_path}")
    else:
        # Running as a script (development)
        # Assume syncthing is in PATH or use shutil.which
        import shutil
        executable_path = shutil.which('syncthing')
        logger.debug(f"Running from script, found syncthing via which: {executable_path}")

    if executable_path and os.path.exists(executable_path):
        logger.info(f"Found Syncthing executable: {executable_path}")
        return executable_path
    else:
        logger.error("Syncthing executable not found.")
        return None

def ensure_syncthing_config_dir():
    """Ensures the Syncthing configuration directory exists."""
    if not os.path.exists(SYNCTHING_CONFIG_DIR):
        logger.info(f"Creating Syncthing config directory: {SYNCTHING_CONFIG_DIR}")
        try:
            os.makedirs(SYNCTHING_CONFIG_DIR, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create Syncthing config directory: {e}")
            return False
    return True

def start_syncthing_daemon(api_address=DEFAULT_SYNCTHING_API_ADDRESS):
    """Starts the Syncthing daemon process."""
    syncthing_exe = get_syncthing_executable_path()
    if not syncthing_exe:
        return None, "Syncthing executable not found."

    if not ensure_syncthing_config_dir():
        return None, "Failed to create Syncthing config directory."

    # Ensure log directory exists
    os.makedirs(os.path.dirname(SYNCTHING_LOG_FILE), exist_ok=True)

    # Command to start Syncthing
    # --home: Use our dedicated config directory
    # --no-browser: Don't open the web UI automatically
    # --gui-address: Specify where the API/GUI listens
    # --logfile: Redirect Syncthing's logs
    # --log-max-old-files=3: Keep only a few old log files
    cmd = [
        syncthing_exe,
        f"--home={SYNCTHING_CONFIG_DIR}",
        "--no-browser",
        f"--gui-address={api_address}",
        f"--logfile={SYNCTHING_LOG_FILE}",
        "--log-max-old-files=3"
    ]

    logger.info(f"Starting Syncthing daemon with command: {' '.join(cmd)}")
    try:
        # Start the process without waiting for it.
        # Redirect stdout/stderr to DEVNULL if not needed, or capture if debugging is required.
        # Use DETACHED_PROCESS on Windows, start_new_session on Unix-like to prevent it
        # being killed when the parent (TurboSync) exits unexpectedly.
        creationflags = 0
        start_new_session = False
        if platform.system() == "Windows":
            # DETACHED_PROCESS makes it a completely separate process
            creationflags = subprocess.DETACHED_PROCESS
        else: # macOS/Linux
            # start_new_session makes it the leader of a new process group
            start_new_session = True

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL, # Or subprocess.PIPE for debugging
            stderr=subprocess.DEVNULL, # Or subprocess.PIPE for debugging
            creationflags=creationflags,
            start_new_session=start_new_session
        )
        logger.info(f"Syncthing daemon started successfully (PID: {process.pid}).")
        # Give it a moment to start up before trying to connect
        time.sleep(2)
        return process, None # Return the process object and no error
    except Exception as e:
        logger.exception(f"Failed to start Syncthing daemon: {e}")
        return None, f"Failed to start Syncthing: {e}"

def stop_syncthing_daemon(process):
    """Stops the Syncthing daemon process."""
    if process and process.poll() is None: # Check if process exists and is running
        logger.info(f"Attempting to terminate Syncthing daemon (PID: {process.pid})...")
        try:
            # Ask Syncthing to shut down gracefully via terminate() (sends SIGTERM)
            process.terminate()
            try:
                # Wait for a short period for graceful shutdown
                process.wait(timeout=10)
                logger.info("Syncthing daemon terminated gracefully.")
            except subprocess.TimeoutExpired:
                logger.warning("Syncthing daemon did not terminate gracefully, killing...")
                process.kill() # Force kill if terminate fails
                process.wait() # Wait for kill to complete
                logger.info("Syncthing daemon killed.")
        except Exception as e:
            logger.error(f"Error stopping Syncthing daemon: {e}")
            # Attempt to kill forcefully if terminate failed unexpectedly
            try:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                    logger.info("Syncthing daemon killed after error during termination.")
            except Exception as kill_err:
                 logger.error(f"Error force killing Syncthing daemon: {kill_err}")
    elif process:
        logger.info("Syncthing daemon was already stopped.")
    else:
        logger.info("No Syncthing process object to stop.")

def is_syncthing_running(process):
    """Checks if the managed Syncthing process is running."""
    if process and process.poll() is None:
        return True
    return False

# --- Placeholder for API Client ---
# class SyncthingApiClient:
#     def __init__(self, api_key, address="127.0.0.1:8385"):
#         self.api_key = api_key
#         self.base_url = f"http://{address}/rest"
#         self.headers = {'X-API-Key': self.api_key}
#         # TODO: Add methods for API interaction using requests library
