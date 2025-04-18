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
USER_LOG_DIR = os.path.expanduser('~/Library/Logs/TurboSync')

# Instance-specific paths
SYNCTHING_CONFIG_DIR_SOURCE = os.path.join(USER_CONFIG_DIR, 'syncthing_config_source')
SYNCTHING_CONFIG_DIR_DEST = os.path.join(USER_CONFIG_DIR, 'syncthing_config_dest')
SYNCTHING_LOG_FILE_SOURCE = os.path.join(USER_LOG_DIR, 'syncthing_source.log')
SYNCTHING_LOG_FILE_DEST = os.path.join(USER_LOG_DIR, 'syncthing_dest.log')


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
        # 1. Check project root directory first
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        root_executable_path = os.path.join(project_root, 'syncthing')
        logger.debug(f"Running from script, checking project root: {root_executable_path}")
        if os.path.exists(root_executable_path) and os.access(root_executable_path, os.X_OK):
            executable_path = root_executable_path
            logger.debug(f"Found syncthing in project root: {executable_path}")
        else:
            # 2. Fallback to checking system PATH
            logger.debug("Syncthing not found in project root, checking system PATH...")
            import shutil
            executable_path = shutil.which('syncthing')
            logger.debug(f"Found syncthing via which: {executable_path}")

    if executable_path and os.path.exists(executable_path):
        # Ensure the found executable is actually executable
        if not os.access(executable_path, os.X_OK):
            logger.error(f"Found Syncthing at {executable_path}, but it is not executable.")
            return None
        logger.info(f"Using Syncthing executable: {executable_path}")
        return executable_path
    else:
        logger.error("Syncthing executable not found.")
        return None

def ensure_dir_exists(dir_path):
    """Ensures the specified directory exists."""
    if not os.path.exists(dir_path):
        logger.info(f"Creating directory: {dir_path}")
        try:
            os.makedirs(dir_path, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {dir_path}: {e}")
            return False
    return True

def start_syncthing_daemon(instance_id, config_dir, api_address, gui_address, log_file):
    """
    Starts a specific Syncthing daemon instance.

    Args:
        instance_id (str): Identifier like "source" or "dest".
        config_dir (str): Path to the configuration directory for this instance.
        api_address (str): API listen address (e.g., "127.0.0.1:28384").
        gui_address (str): GUI listen address (e.g., "127.0.0.1:28385").
        log_file (str): Path to the log file for this instance.
    """
    syncthing_exe = get_syncthing_executable_path()
    if not syncthing_exe:
        return None, "Syncthing executable not found."

    if not ensure_dir_exists(config_dir):
        return None, f"Failed to create Syncthing config directory for {instance_id}: {config_dir}"

    ensure_dir_exists(os.path.dirname(log_file)) # Ensure log directory exists

    # Command to start Syncthing
    # --home: Use our dedicated config directory
    # --no-browser: Don't open the web UI automatically
    # --gui-address: Specify where the API/GUI listens
    # --logfile: Redirect Syncthing's logs
    # --log-max-old-files=3: Keep only a few old log files
    cmd = [
        syncthing_exe,
        f"--home={config_dir}",
        "--no-browser",
        f"--gui-address={gui_address}", # Use separate GUI address
        f"--listen={api_address}",      # Explicitly set API listen address
        f"--logfile={log_file}",
        "--log-max-old-files=3"
    ]
    # Note: --listen sets the API address. --gui-address sets the GUI address.
    # If using Syncthing < 1.19, the API might listen on the gui-address.
    # If using Syncthing >= 1.19, explicitly setting --api is preferred.
    # For broader compatibility, we might rely on gui-address for API initially,
    # or add logic to check Syncthing version if needed.
    # Let's assume for now gui-address works for API for broader compatibility.
    # If issues arise, add the --api flag.

    logger.info(f"Starting Syncthing daemon ({instance_id}) with command: {' '.join(cmd)}")
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

import requests # Import requests library

# --- Syncthing API Client ---
class SyncthingApiClient:
    def __init__(self, api_key, address):
        if not api_key:
             raise ValueError("API key is required for SyncthingApiClient")
        self.api_key = api_key
        # Ensure address includes protocol
        if not address.startswith(('http://', 'https://')):
             # Default to http if not specified, consider https if needed
             self.base_url = f"http://{address}/rest"
             logger.warning(f"API address '{address}' missing protocol, assuming http.")
        else:
             # Ensure it ends with /rest
             if not address.endswith('/rest'):
                  # Remove trailing slash if present before adding /rest
                  self.base_url = address.rstrip('/') + "/rest"
             else:
                  self.base_url = address # Already includes /rest

        self.headers = {'X-API-Key': self.api_key}
        logger.info(f"Syncthing API Client initialized for base URL: {self.base_url}")
        # Test connection on init? Maybe not, do it lazily.

    def _request(self, method, endpoint, params=None, json=None):
        """Internal helper to make API requests."""
        url = self.base_url + endpoint
        try:
            response = requests.request(
                method,
                url,
                headers=self.headers,
                params=params,
                json=json,
                timeout=10 # Add a timeout
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            # Handle empty response body for non-GET requests or specific endpoints
            if response.status_code == 204 or not response.content:
                 return {} # Return empty dict for no content
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Syncthing API request failed ({method} {url}): {e}")
            return None # Indicate failure

    def get_config(self):
        """Get the current Syncthing configuration."""
        return self._request('GET', '/config')

    def update_config(self, config_data):
        """Update the Syncthing configuration."""
        # Note: This replaces the entire config. Use with caution.
        # Consider using specific endpoints for adding/removing devices/folders if needed.
        logger.warning("Attempting to update entire Syncthing config.")
        return self._request('POST', '/config', json=config_data)

    def get_folder_status(self, folder_id):
        """Get status for a specific folder."""
        return self._request('GET', '/db/status', params={'folder': folder_id})

    def get_all_folder_statuses(self):
        """Get status for all configured folders by iterating."""
        # Note: There isn't a single endpoint for all folder statuses.
        # We need to get the config first, then query each folder.
        config = self.get_config()
        if not config or 'folders' not in config:
            logger.warning("Could not get config or no folders found to fetch status.")
            return {} # Return empty dict if config fails or no folders
        statuses = {}
        for f in config['folders']:
            folder_id = f.get('id')
            if folder_id:
                 status = self.get_folder_status(folder_id)
                 if status is not None: # Only add if request was successful
                     # Add the folder label to the status for easier use in UI
                     status['label'] = f.get('label', folder_id)
                     statuses[folder_id] = status
                 else:
                     logger.warning(f"Failed to get status for folder: {folder_id}")
            else:
                 logger.warning(f"Folder found in config without an ID: {f}")
        # Return only statuses where the request succeeded
        return statuses


    def restart_syncthing(self):
        """Trigger a restart of the Syncthing daemon."""
        logger.info("Requesting Syncthing daemon restart via API...")
        response_data = self._request('POST', '/system/restart')
        if response_data is not None: # Check if request itself succeeded
             logger.info("Syncthing restart request sent successfully.")
             return True
        else:
             logger.error("Failed to send Syncthing restart request.")
             return False

    def get_connections(self):
        """Get information about current connections."""
        return self._request('GET', '/system/connections')

    # --- Helper methods for modifying config structure (use before calling update_config) ---

    @staticmethod
    def add_folder_to_config(config_data, folder_id, local_path, devices=None):
        """Adds a folder definition to a config dictionary (does not apply it)."""
        if devices is None:
            devices = [] # Default to empty list if no devices specified
        if 'folders' not in config_data:
            config_data['folders'] = []

        # Check if folder already exists
        for i, folder in enumerate(config_data['folders']):
            if folder.get('id') == folder_id:
                logger.warning(f"Folder '{folder_id}' already exists in config. Updating path and devices.")
                config_data['folders'][i]['path'] = local_path
                config_data['folders'][i]['devices'] = [{'deviceID': dev_id} for dev_id in devices]
                return # Exit after updating

        # Add new folder if not found
        config_data['folders'].append({
            "id": folder_id,
            "label": os.path.basename(local_path) or folder_id, # Use basename as label
            "path": local_path,
            "type": "sendreceive", # Default type
            "devices": [{'deviceID': dev_id} for dev_id in devices],
            "rescanIntervalS": 3600, # Default rescan interval
            "fsWatcherEnabled": True, # Enable watcher if available
            # Add other necessary default folder settings here
        })
        logger.info(f"Prepared folder '{folder_id}' ({local_path}) for addition to config.")

    @staticmethod
    def parse_folder_status(status_data):
        """Parses the raw folder status dict into a more usable format."""
        if not status_data:
            return {"state": "unknown", "error": "No status data", "completion": 0}

        state = status_data.get('state', 'unknown')
        # Check for pull errors specifically
        pull_errors = status_data.get('pullErrors', [])
        error_msg = None
        if pull_errors and len(pull_errors) > 0:
             # Combine first few error messages if multiple exist
             error_msg = "; ".join([e.get('error', 'Unknown pull error') for e in pull_errors[:3]])
             # If state is idle but there are errors, reflect that
             if state == 'idle':
                 state = 'error' # Override state to 'error' if idle but has pull errors

        global_bytes = status_data.get('globalBytes', 0)
        local_bytes = status_data.get('localBytes', 0)
        completion = 0
        if global_bytes > 0:
            # Ensure completion doesn't exceed 100% due to potential inconsistencies
            completion = min((local_bytes / global_bytes) * 100, 100.0)


        return {
            "state": state, # e.g., "idle", "scanning", "syncing", "error"
            "completion": completion,
            "error": error_msg, # Show first error message
            "raw": status_data # Include raw data if needed
        }
    # Add more static helpers as needed: add_device_to_config, share_folder_in_config, remove_folder_from_config

def get_api_key_from_config(config_dir):
    """Reads the API key directly from Syncthing's config.xml."""
    config_path = os.path.join(config_dir, 'config.xml')
    logger.debug(f"Attempting to read API key from: {config_path}")
    if not os.path.exists(config_path):
        logger.warning(f"Syncthing config file not found at {config_path}")
        return None

    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(config_path)
        root = tree.getroot()
        # Find the gui element and then the apikey element within it
        gui_element = root.find('./gui')
        if gui_element is not None:
            api_key_element = gui_element.find('./apikey')
            if api_key_element is not None and api_key_element.text:
                api_key = api_key_element.text.strip()
                logger.info("Successfully retrieved API key from config.xml")
                return api_key
            else:
                logger.warning("API key element not found or empty in config.xml")
        else:
            logger.warning("GUI element not found in config.xml")
        return None
    except ImportError:
        logger.error("xml.etree.ElementTree not available. Cannot parse config.xml for API key.")
        return None
    except ET.ParseError as e:
        logger.error(f"Error parsing Syncthing config.xml: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error reading API key from config.xml: {e}")
        return None
