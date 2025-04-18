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
        if os.path.exists(root_executable_path):
             if os.access(root_executable_path, os.X_OK):
                 executable_path = root_executable_path
                 logger.debug(f"Found executable syncthing in project root: {executable_path}")
             else:
                 logger.warning(f"Found syncthing in project root ({root_executable_path}), but it lacks execute permissions.")
                 executable_path = None # Treat as not found if not executable
        else:
             logger.debug(f"Syncthing file not found at project root path: {root_executable_path}")
             executable_path = None

        if executable_path is None:
            # 2. Fallback to checking system PATH
            logger.debug("Syncthing not found or not executable in project root, checking system PATH...")
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

# Add this function before start_syncthing_daemon
def generate_syncthing_config(syncthing_exe, config_dir):
    """
    Runs Syncthing with the --generate flag to create initial config files.

    Args:
        syncthing_exe (str): Path to the Syncthing executable.
        config_dir (str): Path to the configuration directory to generate.

    Returns:
        bool: True if generation command executed successfully (exit code 0), False otherwise.
    """
    if not syncthing_exe or not os.path.exists(syncthing_exe):
        logger.error(f"Cannot generate config: Syncthing executable not found at {syncthing_exe}")
        return False

    if not ensure_dir_exists(config_dir):
        logger.error(f"Cannot generate config: Failed to ensure config directory exists at {config_dir}")
        return False

    # Check if config.xml already exists. If so, generation might not be needed or could overwrite.
    # For simplicity, we'll run it anyway, Syncthing might handle this gracefully.
    # If issues arise, add a check here: os.path.exists(os.path.join(config_dir, 'config.xml'))
    config_file_path = os.path.join(config_dir, 'config.xml')
    if os.path.exists(config_file_path):
        logger.debug(f"Config file already exists at {config_file_path}. Running --generate anyway.")
        # Optionally skip generation if file exists and is valid? Needs more complex check.

    cmd = [
        syncthing_exe,
        f"--generate={config_dir}"
    ]
    logger.info(f"Generating initial Syncthing config for: {config_dir} with command: {' '.join(cmd)}")

    try:
        # Run the command and wait for it to complete
        result = subprocess.run(
            cmd,
            capture_output=True, # Capture stdout/stderr
            text=True,
            check=False # Don't raise exception on non-zero exit, check manually
        )

        if result.returncode == 0:
            logger.info(f"Syncthing config generation successful for {config_dir}.")
            logger.debug(f"Syncthing --generate stdout:\n{result.stdout}")
            logger.debug(f"Syncthing --generate stderr:\n{result.stderr}")
            # Check if config file was actually created
            if not os.path.exists(config_file_path):
                 logger.warning(f"Syncthing --generate command succeeded but config file not found at {config_file_path}")
                 # Treat as failure? Or maybe Syncthing decided not to overwrite?
                 # For now, log warning but return True based on exit code.
            return True
        else:
            logger.error(f"Syncthing config generation failed for {config_dir} (Exit Code: {result.returncode}).")
            logger.error(f"Syncthing --generate stdout:\n{result.stdout}")
            logger.error(f"Syncthing --generate stderr:\n{result.stderr}")
            return False
    except Exception as e:
        logger.exception(f"Exception occurred while running Syncthing --generate for {config_dir}: {e}")
        return False

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
        # Add API address if provided
        # Removed --api flag as it's not supported by the user's Syncthing version.
        f"--gui-address={gui_address}", # Use separate GUI address
        f"--logfile={log_file}",
        "--log-max-old-files=3"
    ]

    logger.info(f"Starting Syncthing daemon ({instance_id}) with command: {' '.join(cmd)}")
    process = None # Initialize process to None
    try:
        # Start the process without waiting for it.
        creationflags = 0
        start_new_session = False
        if platform.system() == "Windows":
            creationflags = subprocess.DETACHED_PROCESS
        else: # macOS/Linux
            start_new_session = True

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, # Capture stderr
            creationflags=creationflags,
            start_new_session=start_new_session,
            text=True
        )
        logger.info(f"Syncthing daemon ({instance_id}) process created (PID: {process.pid}). Waiting briefly...")

        # Wait a short time to see if it exits immediately
        time.sleep(3.0) # Increased sleep slightly
        exit_code = process.poll()

        if exit_code is not None:
            # Process exited prematurely
            stderr_output = "Could not read stderr."
            try:
                stderr_output = process.stderr.read()
            except Exception as e:
                logger.error(f"Error reading stderr from failed {instance_id} process: {e}")
            error_msg = f"Syncthing daemon ({instance_id}, PID: {process.pid}) exited immediately with code {exit_code}. Stderr: {stderr_output}"
            logger.error(error_msg)
            return None, error_msg # Return failure
        else:
            # Process is still running after the sleep
            logger.info(f"Syncthing daemon ({instance_id}, PID: {process.pid}) appears to have started successfully.")
            return process, None # Return the running process object

    except Exception as e:
        logger.exception(f"Failed to start Syncthing daemon ({instance_id}): {e}")
        if process and process.poll() is None:
             stop_syncthing_daemon(process) # Clean up if Popen succeeded but subsequent steps failed
        return None, f"Failed to start Syncthing ({instance_id}): {e}"

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

       # Determine Origin and Base URL from address
       if not address.startswith(('http://', 'https://')):
            protocol = "http" # Default protocol
            logger.warning(f"API address '{address}' missing protocol, assuming http.")
            host_address = address # Address is just host:port
       else:
            # Split protocol from the rest
            protocol, rest = address.split('://', 1)
            # Get only the host:port part, discard any path like /rest if present
            host_address = rest.split('/', 1)[0]

       self.origin = f"{protocol}://{host_address}" # e.g., http://127.0.0.1:28387
       self.base_url = f"{self.origin}/rest" # Construct base URL for API calls

       # Use ONLY the Authorization header, matching the successful curl command
       self.headers = {'Authorization': f'Bearer {self.api_key}'}
       logger.info(f"Syncthing API Client initialized for base URL: {self.base_url}")
       # Test connection on init? Maybe not, do it lazily.

    def _request(self, method, endpoint, params=None, json=None):
        """Internal helper to make API requests."""
        url = self.base_url + endpoint
        try:
            # Log the request without explicitly mentioning the header type, as it might change
            logger.debug(f"Sending API request: {method} {url}")
            # --- End added line ---
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
        logger.warning("Attempting to update entire Syncthing config using PUT.")
        return self._request('PUT', '/config', json=config_data) # Changed method to PUT

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

    def ping(self):
        """Pings the Syncthing API to check connectivity and authentication."""
        logger.debug(f"Pinging Syncthing API at {self.base_url}/system/ping")
        response = self._request('POST', '/system/ping') # Use POST method matching successful curl
        if response is not None and isinstance(response, dict) and response.get('ping') == 'pong':
            logger.info(f"Syncthing API ping successful for {self.base_url}")
            return True
        else:
            logger.error(f"Syncthing API ping failed for {self.base_url}. Response: {response}")
            return False

    def get_system_status(self):
        """Gets the system status, which typically includes the local device ID ('myID')."""
        logger.debug(f"Getting system status from {self.base_url}/system/status")
        return self._request('GET', '/system/status')

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
    def add_device_to_config(config_data, device_id, device_name):
        """Adds a device definition to a config dictionary (does not apply it)."""
        if 'devices' not in config_data:
            config_data['devices'] = []

        # Check if device already exists
        for device in config_data['devices']:
            if device.get('deviceID') == device_id:
                logger.debug(f"Device '{device_id}' ({device_name}) already exists in config.")
                # Optionally update name or other properties here if needed
                # device['name'] = device_name
                return # Exit if already exists

        # Add new device if not found
        config_data['devices'].append({
            "deviceID": device_id,
            "name": device_name,
            # Add other necessary default device settings here (e.g., introducer=False)
            "introducer": False,
            "autoAcceptFolders": False, # Be explicit about security settings
        })
        logger.info(f"Prepared device '{device_id}' ({device_name}) for addition to config.")

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

    def check_health(self):
        """Checks the /rest/noauth/health endpoint (does not require API key)."""
        # Construct URL without /rest, as health check is relative to base address
        health_url = self.base_url.replace('/rest', '') + '/noauth/health'
        logger.debug(f"Performing health check on: {health_url}")
        try:
            # Make request without API key header and shorter timeout
            response = requests.get(health_url, timeout=2)
            response.raise_for_status() # Check for HTTP errors
            logger.debug(f"Health check successful (Status: {response.status_code})")
            return True # Or return response.json() if needed
        except requests.exceptions.RequestException as e:
            logger.debug(f"Health check failed: {e}")
            return False
        except Exception as e: # Catch other potential errors
            logger.error(f"Unexpected error during health check: {e}")
            return False

    # Add more static helpers as needed: add_device_to_config, share_folder_in_config, remove_folder_from_config

def get_api_key_from_config(config_dir, retries=15, delay=0.75): # Increased retries and delay
    """
    Reads the API key directly from Syncthing's config.xml.
    Retries for a short period to allow Syncthing time to generate the file.
    """
    config_path = os.path.join(config_dir, 'config.xml')
    logger.debug(f"Attempting to read API key from: {config_path} (will retry up to {retries} times)")

    logger.debug(f"Entering retry loop for {config_dir}...") # Added log
    for attempt in range(retries):
        logger.debug(f"API Key Retrieval Attempt {attempt + 1}/{retries} for {config_dir}")
        if os.path.exists(config_path):
            logger.debug(f"  Config file exists: {config_path}")
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(config_path)
                logger.debug("  Successfully parsed config.xml")
                root = tree.getroot()
                gui_element = root.find('./gui')
                if gui_element is not None:
                    logger.debug("  Found 'gui' element")
                    api_key_element = gui_element.find('./apikey')
                    if api_key_element is not None:
                         logger.debug("  Found 'apikey' element")
                         if api_key_element.text:
                             api_key = api_key_element.text.strip()
                             if api_key: # Ensure key is not empty after stripping
                                 logger.info(f"Successfully retrieved API key from config.xml (attempt {attempt + 1})")
                                 return api_key
                             else:
                                 logger.debug(f"  API key element text is empty or whitespace (attempt {attempt + 1}). Retrying...")
                         else:
                              logger.debug(f"  API key element has no text content (attempt {attempt + 1}). Retrying...")
                    else:
                        logger.debug(f"  'apikey' element not found within 'gui' (attempt {attempt + 1}). Retrying...")
                else:
                    logger.debug(f"  'gui' element not found in config.xml root (attempt {attempt + 1}). Retrying...")

            except ImportError:
                logger.error("xml.etree.ElementTree not available. Cannot parse config.xml for API key.")
                return None # Fatal error, don't retry
            except ET.ParseError as e:
                # Config file might be partially written or invalid XML
                logger.warning(f"  Error parsing Syncthing config.xml (attempt {attempt + 1}): {e}. Retrying...")
            except Exception as e:
                # Catch any other unexpected errors during file reading/parsing
                logger.exception(f"  Unexpected error reading/parsing API key from config.xml (attempt {attempt + 1}): {e}. Retrying...")
        else:
            logger.debug(f"  Config file not found at {config_path} (attempt {attempt + 1}). Retrying...")

        # Wait before the next attempt
        logger.debug(f"  Waiting {delay}s before next attempt...")
        time.sleep(delay)

    logger.error(f"Failed to retrieve API key from {config_path} after {retries} attempts.")
    logger.debug(f"Exiting get_api_key_from_config for {config_dir} - returning None.") # Added log
    return None
