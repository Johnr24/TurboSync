import os
import subprocess
import re # Import regex module
import logging
import shutil # Import shutil module
from dotenv import load_dotenv
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor

# Fix multiprocessing to avoid import warnings
if __name__ == "__main__":
    multiprocessing.freeze_support()

# Use root logger instead of configuring a separate one
# This ensures compatibility with the logging setup in main.py
logger = logging.getLogger(__name__)

# Define default values for configuration settings
DEFAULT_CONFIG = {
    'local_dir': '',
    'sync_interval': 5,
    'use_mounted_volume': True, # Keep this true as it's the primary mode now
    'mounted_volume_path': '',
    'remote_syncthing_device_id': '',
    'syncthing_api_key': '',
    'syncthing_listen_address': '127.0.0.1:8385',
    'watch_local_files': True,
    'watch_delay_seconds': 2,
    'start_at_login': False,
}

def load_config(dotenv_path=None):
    """
    Load configuration from .env file if it exists, otherwise return defaults.
    Prioritizes the file specified by dotenv_path if provided.
    Returns the config dictionary and a boolean indicating if a file was loaded.
    """
    config_loaded_from_file = False
    # Use find_dotenv from python-dotenv to locate the .env file automatically
    # if no specific path is given. This handles searching parent directories.
    from dotenv import find_dotenv, dotenv_values
    effective_dotenv_path = dotenv_path or find_dotenv() # Use find_dotenv if no path specified

    if effective_dotenv_path and os.path.exists(effective_dotenv_path):
        logger.info(f"Loading configuration from: {effective_dotenv_path}")
        # Use dotenv_values to get dict without modifying os.environ directly initially
        loaded_values = dotenv_values(dotenv_path=effective_dotenv_path)
        config_loaded_from_file = True
        logger.debug(f"Values loaded from file: {loaded_values}")
    else:
        logger.info(f"No .env file found at '{effective_dotenv_path}'. Using default configuration values.")
        loaded_values = {} # Start with empty dict, defaults will apply

    # Build config dictionary, applying loaded values over defaults
    config = {}
    config['local_dir'] = loaded_values.get('LOCAL_DIR', DEFAULT_CONFIG['local_dir'])
    config['sync_interval'] = int(loaded_values.get('SYNC_INTERVAL', DEFAULT_CONFIG['sync_interval']))
    config['use_mounted_volume'] = True # Always true
    config['mounted_volume_path'] = loaded_values.get('MOUNTED_VOLUME_PATH', DEFAULT_CONFIG['mounted_volume_path'])
    config['remote_syncthing_device_id'] = loaded_values.get('REMOTE_SYNCTHING_DEVICE_ID', DEFAULT_CONFIG['remote_syncthing_device_id'])
    config['syncthing_api_key'] = loaded_values.get('SYNCTHING_API_KEY', DEFAULT_CONFIG['syncthing_api_key'])
    config['syncthing_listen_address'] = loaded_values.get('SYNCTHING_LISTEN_ADDRESS', DEFAULT_CONFIG['syncthing_listen_address'])
    config['watch_local_files'] = str(loaded_values.get('WATCH_LOCAL_FILES', str(DEFAULT_CONFIG['watch_local_files']))).lower() == 'true'
    config['watch_delay_seconds'] = int(loaded_values.get('WATCH_DELAY_SECONDS', DEFAULT_CONFIG['watch_delay_seconds']))
    config['start_at_login'] = str(loaded_values.get('START_AT_LOGIN', str(DEFAULT_CONFIG['start_at_login']))).lower() == 'true'

    # Add the flag indicating source
    config['loaded_from_file'] = config_loaded_from_file

    # --- Validation ---
    # Only perform strict validation if the config was loaded from a file
    # If using defaults, assume configuration is needed.
    config['is_valid'] = False # Assume invalid until proven otherwise
    config['validation_message'] = "Configuration not loaded from file. Please configure via Settings."
    config['is_mounted'] = False # Default to false

    if config_loaded_from_file:
        # Essential keys if loaded from file: Local directory, path to the mounted source volume, and the remote Syncthing ID
        required_keys = ['local_dir', 'mounted_volume_path', 'remote_syncthing_device_id']
        missing_keys = [key for key in required_keys if not config.get(key)]

        if missing_keys:
            config['validation_message'] = f"Missing required configuration: {', '.join(missing_keys)}"
            logger.error(f"Configuration loaded from file is invalid: {config['validation_message']}")
        else:
            # Check if the mounted volume path exists
            if os.path.exists(config['mounted_volume_path']):
                logger.info(f"Using configured mounted volume: {config['mounted_volume_path']}")
                config['mounted_path'] = config['mounted_volume_path'] # Use 'mounted_path' internally
                config['is_mounted'] = True # Keep this flag for clarity elsewhere
                config['is_valid'] = True # Configuration is valid
                config['validation_message'] = "Configuration loaded and valid."
                logger.info("Configuration loaded from file is valid.")
            else:
                # If the specified path doesn't exist, it's a fatal configuration error *for this loaded config*
                config['validation_message'] = f"Configured MOUNTED_VOLUME_PATH not found: {config['mounted_volume_path']}"
                logger.error(f"Configuration loaded from file is invalid: {config['validation_message']}")
                # Do not raise ValueError here, let the caller handle invalid state

    # Log final configuration state
    logger.info(f"Configuration State: {'Loaded from file' if config_loaded_from_file else 'Using defaults'}, Valid: {config['is_valid']}")
    if not config['is_valid']:
         logger.warning(f"Configuration issue: {config['validation_message']}")
    # Log key values regardless of validity for debugging
    logger.info(f"  Mounted Volume Path (Source): {config.get('mounted_path', config['mounted_volume_path'])}") # Show mounted_path if set
    logger.info(f"  Local Directory (Destination): {config['local_dir']}")
    logger.info(f"  Sync Interval: {config['sync_interval']} minutes")
    logger.info(f"  Remote Syncthing Device ID: {config['remote_syncthing_device_id']}")
    logger.info(f"  Local Syncthing API Address: {config['syncthing_listen_address']}")
    logger.info(f"  Local File Watching: {config['watch_local_files']}")
    if config['watch_local_files']:
        logger.info(f"  File Watch Delay: {config['watch_delay_seconds']} seconds")
    logger.info(f"  Start at Login: {config['start_at_login']}")

    return config # Return the dictionary, caller checks 'is_valid'

# Removed test_remote_connection (SSH specific, only used for initial check, not core sync)

def find_livework_dirs(config):
    """Find directories with .livework files on the remote server or mounted volume"""
    logger.info("Scanning for .livework files")
    
    livework_dirs = []
    mounted_path = config.get('mounted_path') # Get the validated mounted path

    if not mounted_path:
        logger.error("Mounted path configuration is missing, cannot scan for .livework files.")
        return []

    logger.info(f"Searching for .livework files in mounted volume: {mounted_path}")

    try:
        # Log the top-level directory contents for debugging
        if os.path.exists(mounted_path):
            logger.debug(f"Contents of mounted directory: {mounted_path}")
            try:
                entries = os.listdir(mounted_path)
                for entry in entries:
                    logger.debug(f"  - {entry}")
            except Exception as e:
                logger.error(f"Error listing mounted directory contents: {e}")
            
            # Walk the directory tree to find .livework files
            logger.info("Beginning directory walk to find .livework files...")
            for root, dirs, files in os.walk(mounted_path):
                logger.debug(f"Checking directory: {root}")
                # Check for both '.livework' (hidden) and 'livework' (visible) files
                if '.livework' in files or 'livework' in files:
                    livework_dirs.append(root)
                    logger.info(f"Found .livework in: {root}")
            
            logger.info(f"Found {len(livework_dirs)} directories with .livework files.")
        else:
             logger.error(f"Mounted directory does not exist: {mounted_path}")
             return []

    except Exception as e:
        logger.error(f"Error finding .livework directories in mounted volume: {str(e)}")
        return []

    return livework_dirs

# Removed list_remote_directory (SSH specific, not core sync)
# Removed sync_directory (rsync specific)
# Removed perform_sync (rsync specific)

# --- New Syncthing Configuration Update Logic ---
from .syncthing_manager import SyncthingApiClient, get_api_key_from_config, SYNCTHING_CONFIG_DIR, DEFAULT_SYNCTHING_API_ADDRESS

def update_syncthing_configuration():
    """
    Finds .livework directories, compares with current Syncthing config,
    and updates the Syncthing daemon's configuration via API.
    """
    logger.info("Starting Syncthing configuration update process...")
    config_updated = False
    error_occurred = False
    message = "Configuration update check completed."

    try:
        # 1. Load TurboSync Configuration
        user_env_path = os.path.join(os.path.expanduser(f'~/Library/Application Support/TurboSync'), '.env')
        config = load_config(dotenv_path=user_env_path) # load_config now returns dict always

        # --- Check if config is valid before proceeding ---
        if not config or not config.get('is_valid'):
             message = config.get('validation_message', "Configuration is invalid or missing.")
             logger.error(f"Cannot update Syncthing configuration: {message}")
             # Return error state without raising exception here, let caller handle UI
             return False, f"Config Error: {message}"

        # Config is valid, proceed with extracting values
        local_base_dir = config['local_dir']
        remote_device_id = config['remote_syncthing_device_id']
        api_addr = config.get('syncthing_listen_address', DEFAULT_SYNCTHING_API_ADDRESS)
        api_key = config.get('syncthing_api_key')

        # 2. Initialize Syncthing API Client
        if not api_key:
            logger.info("SYNCTHING_API_KEY not in .env, attempting to retrieve from config.xml...")
            api_key = get_api_key_from_config(config_dir=SYNCTHING_CONFIG_DIR)
            if not api_key:
                raise ValueError("Syncthing API key not found in .env or config.xml. Cannot update configuration.")
            logger.info("Successfully retrieved API key from config.xml.")

        api_client = SyncthingApiClient(api_key=api_key, address=api_addr)

        # 3. Find .livework Directories
        # find_livework_dirs uses remote_dir (SSH) or mounted_path (local) from config
        logger.info("Scanning for .livework directories...")
        livework_remote_paths = find_livework_dirs(config)
        if not livework_remote_paths:
            logger.warning("No .livework directories found.")
            # Decide if we should remove all folders from Syncthing config in this case?
            # For now, just log and proceed to check existing config.

        # Map found source paths (from mounted volume) to desired local paths and folder IDs
        desired_folders = {} # {folder_id: {'local_path': '/path/to/local', 'source_path': '/path/to/source'}}
        base_mounted_path = config['mounted_path'] # Use the validated mounted path

        for source_path in livework_remote_paths: # Variable name kept for now, but it's the source path on the mount
            # Derive local path relative to the local_base_dir
            if source_path == base_mounted_path:
                rel_path = '.' # Sync the base directory itself if it has .livework
            else:
                try:
                    # Calculate path relative to the base of the mounted volume
                    rel_path = os.path.relpath(source_path, base_mounted_path)
                except ValueError as e:
                    # This might happen if paths are fundamentally different (e.g., different drives on Windows, though unlikely here)
                    rel_path = os.path.basename(source_path)
                    logger.warning(f"Could not determine relative path for '{source_path}' relative to '{base_mounted_path}'. Using basename '{rel_path}'. Error: {e}")

            local_path = os.path.normpath(os.path.join(local_base_dir, rel_path))
            # Create a reasonably unique folder ID (e.g., based on relative path)
            # Replace path separators with underscores for Syncthing ID compatibility
            # Ensure ID is valid (Syncthing IDs have restrictions)
            folder_id = re.sub(r'[\\/:"*?<>|]+', '_', rel_path) # Replace invalid chars
            folder_id = folder_id.replace(' ', '_').replace('.', '_livework') # Replace space and dot
            if not folder_id or folder_id == '_livework': # Handle base directory case
                 folder_id = os.path.basename(local_base_dir) + '_livework_base'
            # Truncate if too long (Syncthing might have limits) - adjust limit as needed
            folder_id = folder_id[:64] # Example limit

            # Ensure local directory exists (Syncthing might need it)
            os.makedirs(local_path, exist_ok=True)

            desired_folders[folder_id] = {'local_path': local_path, 'source_path': source_path}
            logger.debug(f"Desired folder: ID='{folder_id}', Local='{local_path}', Source='{source_path}'")

        # 4. Get Current Syncthing Configuration
        logger.info("Fetching current Syncthing configuration via API...")
        current_st_config = api_client.get_config()
        if current_st_config is None:
            raise ConnectionError("Failed to fetch current Syncthing configuration from API.")

        # Make a deep copy to modify safely
        import copy
        new_st_config = copy.deepcopy(current_st_config)
        if 'folders' not in new_st_config: new_st_config['folders'] = []
        if 'devices' not in new_st_config: new_st_config['devices'] = []

        # 5. Get Local Device ID
        local_device_id = None
        if 'devices' in new_st_config:
            # Find the device entry that corresponds to the local instance
            # This is often the first device listed or identified by name="localhost" or similar
            # A more robust way might be needed if the config is complex.
            # For now, assume the first device is local if only one exists, or look for clues.
            # A better approach: Call /system/status to get the local device ID ('myID')
            system_status = api_client._request('GET', '/system/status')
            if system_status and 'myID' in system_status:
                local_device_id = system_status['myID']
                logger.info(f"Got local Syncthing device ID: {local_device_id}")
            else:
                 logger.warning("Could not determine local Syncthing device ID from API. Configuration update might be incomplete.")
                 # Fallback: Try finding it in the config devices list (less reliable)
                 # for dev in new_st_config['devices']:
                 #    # Heuristic: Check for common local names or lack of address
                 #    if dev.get('name') == platform.node() or not dev.get('address'):
                 #         local_device_id = dev.get('deviceID')
                 #         logger.warning(f"Guessed local device ID from config: {local_device_id}")
                 #         break

        # 6. Compare and Update Folders
        current_folder_ids = {f.get('id') for f in new_st_config['folders']}
        desired_folder_ids = set(desired_folders.keys())

        folders_to_add = desired_folder_ids - current_folder_ids
        folders_to_remove = current_folder_ids - desired_folder_ids
        folders_to_keep = current_folder_ids.intersection(desired_folder_ids)

        # Remove folders no longer desired
        if folders_to_remove:
            logger.info(f"Removing {len(folders_to_remove)} folders from Syncthing config: {folders_to_remove}")
            new_st_config['folders'] = [f for f in new_st_config['folders'] if f.get('id') not in folders_to_remove]
            config_updated = True

        # Add new folders
        for folder_id in folders_to_add:
            local_path = desired_folders[folder_id]['local_path']
            logger.info(f"Adding folder '{folder_id}' ({local_path}) to Syncthing config.")
            # Use helper method to add folder structure
            SyncthingApiClient.add_folder_to_config(
                new_st_config,
                folder_id,
                local_path,
                devices=[remote_device_id] # Share with remote device by default
            )
            config_updated = True

        # Update existing folders (path, sharing) - ensure they are shared with the remote device
        for folder_id in folders_to_keep:
             for i, folder in enumerate(new_st_config['folders']):
                 if folder.get('id') == folder_id:
                     # Ensure path matches (it might change if local_dir changes)
                     expected_local_path = desired_folders[folder_id]['local_path']
                     if folder.get('path') != expected_local_path:
                          logger.warning(f"Updating path for existing folder '{folder_id}': '{folder.get('path')}' -> '{expected_local_path}'")
                          new_st_config['folders'][i]['path'] = expected_local_path
                          config_updated = True

                     # Ensure it's shared with the configured remote device
                     shared_devices = {d.get('deviceID') for d in folder.get('devices', [])}
                     if remote_device_id not in shared_devices:
                         logger.info(f"Sharing existing folder '{folder_id}' with remote device '{remote_device_id}'.")
                         if 'devices' not in new_st_config['folders'][i]:
                             new_st_config['folders'][i]['devices'] = []
                         # Avoid adding duplicate device entries
                         if not any(d.get('deviceID') == remote_device_id for d in new_st_config['folders'][i]['devices']):
                              new_st_config['folders'][i]['devices'].append({'deviceID': remote_device_id})
                              config_updated = True
                     break # Move to next folder_id

        # 7. Ensure Remote Device Exists
        current_device_ids = {d.get('deviceID') for d in new_st_config['devices']}
        if remote_device_id not in current_device_ids:
            logger.info(f"Adding remote device '{remote_device_id}' to Syncthing config.")
            new_st_config['devices'].append({
                "deviceID": remote_device_id,
                "name": f"Remote TurboSync Device ({remote_device_id[:7]}...)", # Give it a default name
                "addresses": ["dynamic"], # Let Syncthing discover it
                "introducer": False,
                # Add other necessary default device settings
            })
            config_updated = True

        # 8. Apply Configuration Changes (if any)
        if config_updated:
            logger.info("Applying updated configuration to Syncthing via API...")
            success = api_client.update_config(new_st_config)
            if success is None: # Check for API request failure
                 message = "Error: Failed to apply updated Syncthing configuration via API."
                 logger.error(message)
                 error_occurred = True
            else:
                 message = f"Syncthing configuration updated successfully. Added: {len(folders_to_add)}, Removed: {len(folders_to_remove)}."
                 logger.info(message)
                 # Optional: Trigger a restart if needed, though Syncthing often reloads config automatically
                 # api_client.restart_syncthing()
        else:
            message = "No Syncthing configuration changes needed."
            logger.info(message)

    except ValueError as e: # Catch config loading errors or API key issues
        logger.error(f"Configuration error during Syncthing update: {str(e)}")
        message = f"Config Error: {str(e)}"
        error_occurred = True
    except ConnectionError as e:
        logger.error(f"API connection error during Syncthing update: {str(e)}")
        message = f"API Error: {str(e)}"
        error_occurred = True
    except Exception as e:
        logger.error(f"Unexpected error during Syncthing configuration update: {str(e)}")
        logger.exception("Traceback:")
        message = f"Unexpected Error: {str(e)}"
        error_occurred = True

    logger.info(f"Syncthing configuration update finished. Status: {'Error' if error_occurred else 'OK'}, Message: {message}")
    return not error_occurred, message # Return success status and message
