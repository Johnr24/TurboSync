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
    'source_dir': '', # Renamed from mounted_volume_path
    'local_dir': '',
    'sync_interval': 5,
    'watch_local_files': True,
    'watch_delay_seconds': 2,
    'start_at_login': False,
    # Syncthing Instance A (Source) Defaults
    'syncthing_api_address_source': '127.0.0.1:28384', # Changed port
    'syncthing_gui_address_source': '127.0.0.1:28385', # Changed port
    # 'syncthing_api_key_source': '', # Removed - Auto-retrieved
    # Syncthing Instance B (Destination) Defaults
    'syncthing_api_address_dest': '127.0.0.1:28386', # Changed port
    'syncthing_gui_address_dest': '127.0.0.1:28387', # Changed port
    # 'syncthing_api_key_dest': '', # Removed - Auto-retrieved
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
    config['source_dir'] = loaded_values.get('SOURCE_DIR', DEFAULT_CONFIG['source_dir'])
    config['local_dir'] = loaded_values.get('LOCAL_DIR', DEFAULT_CONFIG['local_dir'])
    config['sync_interval'] = int(loaded_values.get('SYNC_INTERVAL', DEFAULT_CONFIG['sync_interval']))
    # Source Syncthing Instance
    config['syncthing_api_address_source'] = loaded_values.get('SYNCTHING_API_ADDRESS_SOURCE', DEFAULT_CONFIG['syncthing_api_address_source'])
    config['syncthing_gui_address_source'] = loaded_values.get('SYNCTHING_GUI_ADDRESS_SOURCE', DEFAULT_CONFIG['syncthing_gui_address_source'])
    # config['syncthing_api_key_source'] = loaded_values.get('SYNCTHING_API_KEY_SOURCE', DEFAULT_CONFIG['syncthing_api_key_source']) # Removed
    # Destination Syncthing Instance
    config['syncthing_api_address_dest'] = loaded_values.get('SYNCTHING_API_ADDRESS_DEST', DEFAULT_CONFIG['syncthing_api_address_dest'])
    config['syncthing_gui_address_dest'] = loaded_values.get('SYNCTHING_GUI_ADDRESS_DEST', DEFAULT_CONFIG['syncthing_gui_address_dest'])
    # config['syncthing_api_key_dest'] = loaded_values.get('SYNCTHING_API_KEY_DEST', DEFAULT_CONFIG['syncthing_api_key_dest']) # Removed
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
    config['source_dir_exists'] = False # Default to false

    if config_loaded_from_file:
        # Essential keys if loaded from file: Source and Local directories
        required_keys = ['source_dir', 'local_dir']
        missing_keys = [key for key in required_keys if not config.get(key)]

        if missing_keys:
            config['validation_message'] = f"Missing required configuration: {', '.join(missing_keys)}"
            logger.error(f"Configuration loaded from file is invalid: {config['validation_message']}")
        else:
            # Check if the mounted volume path exists
            if os.path.exists(config['source_dir']):
                logger.info(f"Source directory exists: {config['source_dir']}")
                config['source_dir_exists'] = True
                config['is_valid'] = True # Configuration is valid
                config['validation_message'] = "Configuration loaded and valid."
                logger.info("Configuration loaded from file is valid.")
            else:
                # If the specified path doesn't exist, it's a fatal configuration error *for this loaded config*
                config['validation_message'] = f"Configured SOURCE_DIR not found: {config['source_dir']}"
                logger.error(f"Configuration loaded from file is invalid: {config['validation_message']}")
                # Do not raise ValueError here, let the caller handle invalid state

    # Log final configuration state
    logger.info(f"Configuration State: {'Loaded from file' if config_loaded_from_file else 'Using defaults'}, Valid: {config['is_valid']}")
    if not config['is_valid']:
         logger.warning(f"Configuration issue: {config['validation_message']}")
    # Log key values regardless of validity for debugging
    logger.info(f"  Source Directory: {config['source_dir']}")
    logger.info(f"  Local Directory (Destination): {config['local_dir']}")
    logger.info(f"  Sync Interval: {config['sync_interval']} minutes")
    logger.info(f"  Syncthing Source API: {config['syncthing_api_address_source']}")
    logger.info(f"  Syncthing Source GUI: {config['syncthing_gui_address_source']}")
    logger.info(f"  Syncthing Dest API: {config['syncthing_api_address_dest']}")
    logger.info(f"  Syncthing Dest GUI: {config['syncthing_gui_address_dest']}")
    logger.info(f"  Local File Watching: {config['watch_local_files']}")
    if config['watch_local_files']:
        logger.info(f"  File Watch Delay: {config['watch_delay_seconds']} seconds")
    logger.info(f"  Start at Login: {config['start_at_login']}")

    return config # Return the dictionary, caller checks 'is_valid'

# Removed test_remote_connection (SSH specific, only used for initial check, not core sync)

def find_livework_dirs(config):
    """Find directories with .livework files on the remote server or mounted volume"""
    logger.info("Scanning for .livework files")
    
    livework_source_dirs = []
    source_dir = config.get('source_dir') # Get the configured source directory

    if not source_dir:
        logger.error("Source directory configuration is missing, cannot scan for .livework files.")
        return []

    logger.info(f"Searching for .livework files in source directory: {source_dir}")

    try:
        # Log the top-level directory contents for debugging
        if os.path.exists(source_dir):
            logger.debug(f"Contents of source directory: {source_dir}")
            try:
                entries = os.listdir(source_dir)
                for entry in entries:
                    logger.debug(f"  - {entry}")
            except Exception as e:
                logger.error(f"Error listing source directory contents: {e}")
            
            # Walk the directory tree to find .livework files
            logger.info("Beginning directory walk to find .livework files...")
            for root, dirs, files in os.walk(source_dir):
                logger.debug(f"Checking directory: {root}")
                # Check for both '.livework' (hidden) and 'livework' (visible) files
                if '.livework' in files or 'livework' in files:
                    livework_source_dirs.append(root)
                    logger.info(f"Found .livework in: {root}")
            
            logger.info(f"Found {len(livework_source_dirs)} directories with .livework files.")
        else:
             logger.error(f"Source directory does not exist: {source_dir}")
             return []

    except Exception as e:
        logger.error(f"Error finding .livework directories in source directory: {str(e)}")
        return []

    return livework_source_dirs

# Removed list_remote_directory (SSH specific, not core sync)
# Removed sync_directory (rsync specific)
# Removed perform_sync (rsync specific)

# --- New Syncthing Configuration Update Logic ---
from .syncthing_manager import SyncthingApiClient # Keep API client import
# Define APP_NAME here if not already defined globally in this file
APP_NAME = "TurboSync"

def update_syncthing_configuration(api_client_source: SyncthingApiClient, api_client_dest: SyncthingApiClient):
    """
    Finds .livework directories, compares with current Syncthing config,
    and updates BOTH local Syncthing daemon configurations via API to sync
    the corresponding folders between them.

    Args:
        api_client_source: Initialized SyncthingApiClient for the source instance.
        api_client_dest: Initialized SyncthingApiClient for the destination instance.
    """
    logger.info("Starting Syncthing configuration update process...")
    config_updated = False
    error_occurred = False
    message = "Configuration update check completed."

    try:
        # Check if API clients are provided
        if not api_client_source or not api_client_dest:
             raise ValueError("API clients for source and destination instances are required.")

        # 1. Load TurboSync Configuration
        user_env_path = os.path.join(os.path.expanduser(f'~/Library/Application Support/{APP_NAME}'), '.env')
        config = load_config(dotenv_path=user_env_path) # load_config now returns dict always

        # --- Check if config is valid before proceeding ---
        if not config or not config.get('is_valid'):
             message = config.get('validation_message', "Configuration is invalid or missing.")
             logger.error(f"Cannot update Syncthing configuration: {message}")
             # Return error state without raising exception here, let caller handle UI
             return False, f"Config Error: {message}"

        # Config is valid, proceed with extracting values
        local_base_dir = config['local_dir']
        source_base_dir = config['source_dir'] # Renamed from mounted_path

        # API Clients are passed in, no need to initialize here

        # 3. Find .livework Directories
        logger.info("Scanning for .livework directories...")
        livework_source_paths = find_livework_dirs(config) # Returns paths on the source volume
        if not livework_source_paths:
            logger.warning("No .livework directories found.")
            # Decide if we should remove all folders from Syncthing config in this case?
            # For now, just log and proceed to check existing config.
            # TODO: Implement removal logic if desired.

        # Map found source paths (from mounted volume) to desired local paths and folder IDs
        desired_folders = {} # {folder_id: {'dest_path': '/path/to/local', 'source_path': '/path/to/source'}}

        for source_path in livework_source_paths: # Variable name kept for now, but it's the source path on the mount
            # Derive local path relative to the local_base_dir
            if source_path == source_base_dir:
                rel_path = '.' # Sync the base directory itself if it has .livework
            else:
                try:
                    # Calculate path relative to the base of the mounted volume
                    rel_path = os.path.relpath(source_path, source_base_dir)
                except ValueError as e:
                    # This might happen if paths are fundamentally different (e.g., different drives on Windows, though unlikely here)
                    rel_path = os.path.basename(source_path)
                    logger.warning(f"Could not determine relative path for '{source_path}' relative to '{source_base_dir}'. Using basename '{rel_path}'. Error: {e}")

            local_path = os.path.normpath(os.path.join(local_base_dir, rel_path))
            # Create a reasonably unique folder ID (e.g., based on relative path)
            # Replace path separators with underscores for Syncthing ID compatibility
            # Ensure ID is valid (Syncthing IDs have restrictions)
            folder_id = re.sub(r'[\\/:"*?<>|]+', '_', rel_path) # Replace invalid chars
            folder_id = folder_id.replace(' ', '_').replace('.', '_livework') # Replace space and dot
            if not folder_id or folder_id == '_livework': # Handle base directory case
                 # Use basename of the *source* dir for uniqueness if base is synced
                 base_name = os.path.basename(source_base_dir) or "source_base"
                 folder_id = base_name + '_livework_base'
            # Truncate if too long (Syncthing might have limits) - adjust limit as needed
            folder_id = folder_id[:64] # Example limit

            # Ensure local directory exists (Syncthing Destination instance needs it)
            os.makedirs(local_path, exist_ok=True)
            # Source directory already exists (it's where we found .livework)

            # Store both paths for the folder ID
            desired_folders[folder_id] = {'dest_path': local_path, 'source_path': source_path}
            logger.debug(f"Desired folder: ID='{folder_id}', Dest='{local_path}', Source='{source_path}'")

        # 4. Get Current Syncthing Configuration
        # Fetch config for BOTH instances using the provided clients
        logger.info("Fetching current Syncthing configurations via API...")
        current_config_source = api_client_source.get_config()
        current_config_dest = api_client_dest.get_config()
        if current_config_source is None or current_config_dest is None:
             raise ConnectionError("Failed to fetch current Syncthing configuration from one or both APIs.")


        # Make a deep copy to modify safely
        import copy
        new_config_source = copy.deepcopy(current_config_source)
        new_config_dest = copy.deepcopy(current_config_dest)
        if 'folders' not in new_config_source: new_config_source['folders'] = []
        if 'devices' not in new_config_source: new_config_source['devices'] = []
        if 'folders' not in new_config_dest: new_config_dest['folders'] = []
        if 'devices' not in new_config_dest: new_config_dest['devices'] = []


        # 5. Get Local Device ID
        # Get Device IDs for BOTH local instances using the provided clients
        device_id_source = None
        device_id_dest = None

        status_source = api_client_source.get_system_status() # Need a get_system_status method
        if status_source and 'myID' in status_source:
            device_id_source = status_source['myID']
            logger.info(f"Got Source Syncthing Device ID: {device_id_source}")
        else:
            raise ConnectionError("Could not determine Source Syncthing Device ID from API.")

        status_dest = api_client_dest.get_system_status() # Need a get_system_status method
        if status_dest and 'myID' in status_dest:
            device_id_dest = status_dest['myID']
            logger.info(f"Got Destination Syncthing Device ID: {device_id_dest}")
        else:
            raise ConnectionError("Could not determine Destination Syncthing Device ID from API.")

        # 6. Compare and Update Folders
        # --- Update Source Instance Folders ---
        current_folder_ids_source = {f.get('id') for f in new_config_source['folders']}
        desired_folder_ids = set(desired_folders.keys()) # Same desired folders for both

        folders_to_add_source = desired_folder_ids - current_folder_ids_source
        folders_to_remove_source = current_folder_ids_source - desired_folder_ids
        folders_to_keep_source = current_folder_ids_source.intersection(desired_folder_ids)

        # Remove folders no longer desired (Source)
        if folders_to_remove_source:
            logger.info(f"Removing {len(folders_to_remove_source)} folders from Source Syncthing config: {folders_to_remove_source}")
            new_config_source['folders'] = [f for f in new_config_source['folders'] if f.get('id') not in folders_to_remove_source]
            config_updated = True # Mark that *some* config changed

        # Add new folders (Source)
        for folder_id in folders_to_add_source:
            source_path = desired_folders[folder_id]['source_path']
            logger.info(f"Adding folder '{folder_id}' ({source_path}) to Source Syncthing config.")
            SyncthingApiClient.add_folder_to_config(
                new_config_source,
                folder_id,
                source_path, # Use source path for source instance
                devices=[device_id_dest] # Share with Destination instance
            )
            config_updated = True

        # Update existing folders (Source)
        for folder_id in folders_to_keep_source:
             for i, folder in enumerate(new_config_source['folders']):
                 if folder.get('id') == folder_id:
                     # Ensure path matches
                     expected_source_path = desired_folders[folder_id]['source_path']
                     if folder.get('path') != expected_source_path:
                          logger.warning(f"Updating path for existing folder '{folder_id}' in Source config: '{folder.get('path')}' -> '{expected_source_path}'")
                          new_config_source['folders'][i]['path'] = expected_source_path
                          config_updated = True

                     # Ensure it's shared with the Destination device
                     shared_devices = {d.get('deviceID') for d in folder.get('devices', [])}
                     if device_id_dest not in shared_devices:
                         logger.info(f"Sharing existing folder '{folder_id}' in Source config with Dest device '{device_id_dest}'.")
                         if 'devices' not in new_config_source['folders'][i]:
                             new_config_source['folders'][i]['devices'] = []
                         # Ensure the device entry is a dict
                         if not any(isinstance(d, dict) and d.get('deviceID') == device_id_dest for d in new_config_source['folders'][i]['devices']):
                              new_config_source['folders'][i]['devices'].append({'deviceID': device_id_dest})
                              config_updated = True
                     break

        # --- Update Destination Instance Folders ---
        current_folder_ids_dest = {f.get('id') for f in new_config_dest['folders']}
        # desired_folder_ids is the same

        folders_to_add_dest = desired_folder_ids - current_folder_ids_dest
        folders_to_remove_dest = current_folder_ids_dest - desired_folder_ids
        folders_to_keep_dest = current_folder_ids_dest.intersection(desired_folder_ids)

        # Remove folders no longer desired (Dest)
        if folders_to_remove_dest:
            logger.info(f"Removing {len(folders_to_remove_dest)} folders from Dest Syncthing config: {folders_to_remove_dest}")
            new_config_dest['folders'] = [f for f in new_config_dest['folders'] if f.get('id') not in folders_to_remove_dest]
            config_updated = True # Mark that *some* config changed

        # Add new folders (Dest)
        for folder_id in folders_to_add_dest:
            dest_path = desired_folders[folder_id]['dest_path']
            logger.info(f"Adding folder '{folder_id}' ({dest_path}) to Dest Syncthing config.")
            SyncthingApiClient.add_folder_to_config(
                new_config_dest,
                folder_id,
                dest_path, # Use destination path for destination instance
                devices=[device_id_source] # Share with Source instance
            )
            config_updated = True

        # Update existing folders (Dest)
        for folder_id in folders_to_keep_dest:
             for i, folder in enumerate(new_config_dest['folders']):
                 if folder.get('id') == folder_id:
                     # Ensure path matches
                     expected_dest_path = desired_folders[folder_id]['dest_path']
                     if folder.get('path') != expected_dest_path:
                          logger.warning(f"Updating path for existing folder '{folder_id}' in Dest config: '{folder.get('path')}' -> '{expected_dest_path}'")
                          new_config_dest['folders'][i]['path'] = expected_dest_path
                          config_updated = True
                     # Ensure it's shared with the Source device
                     shared_devices_dest = {d.get('deviceID') for d in folder.get('devices', [])}
                     if device_id_source not in shared_devices_dest:
                         logger.info(f"Sharing existing folder '{folder_id}' in Dest config with Source device '{device_id_source}'.")
                         if 'devices' not in new_config_dest['folders'][i]:
                             new_config_dest['folders'][i]['devices'] = []
                         # Ensure the device entry is a dict
                         if not any(isinstance(d, dict) and d.get('deviceID') == device_id_source for d in new_config_dest['folders'][i]['devices']):
                              new_config_dest['folders'][i]['devices'].append({'deviceID': device_id_source})
                              config_updated = True
                     break

        # 7. Ensure Remote Device Exists
        # Ensure BOTH instances know about EACH OTHER's device ID
        # Check Source config for Dest device
        current_device_ids_source = {d.get('deviceID') for d in new_config_source['devices']}
        if device_id_dest not in current_device_ids_source:
            logger.info(f"Adding Dest device '{device_id_dest}' to Source Syncthing config.")
            SyncthingApiClient.add_device_to_config( # Use add_device_to_config helper
                new_config_source,
                device_id_dest,
                f"TurboSync Peer (Dest - {device_id_dest[:7]}...)"
            )
            config_updated = True

        # Check Dest config for Source device
        current_device_ids_dest = {d.get('deviceID') for d in new_config_dest['devices']}
        if device_id_source not in current_device_ids_dest:
             logger.info(f"Adding Source device '{device_id_source}' to Dest Syncthing config.")
             SyncthingApiClient.add_device_to_config( # Use add_device_to_config helper
                 new_config_dest,
                 device_id_source,
                 f"TurboSync Peer (Source - {device_id_source[:7]}...)"
             )
             config_updated = True


        # 8. Apply Configuration Changes (if any)
        # --- RE-ENABLED CONFIG UPDATE ---
        if config_updated:
            logger.info("Applying updated configuration to Syncthing instances via API...")
            # Apply updates to BOTH instances using the provided clients
            success_source = api_client_source.update_config(new_config_source)
            success_dest = api_client_dest.update_config(new_config_dest)

            if success_source is None or success_dest is None: # Check for API request failure on either
                 message = "Error: Failed to apply updated Syncthing configuration via API to one or both instances."
                 logger.error(message)
                 error_occurred = True
            else:
                 # Use the variables calculated for the source instance (should be same count for dest)
                 message = f"Syncthing configuration updated successfully. Added: {len(folders_to_add_source)}, Removed: {len(folders_to_remove_source)}."
                 logger.info(message)
                 # Optional: Trigger a restart if needed, though Syncthing often reloads config automatically
                 # api_client.restart_syncthing()
        else:
            message = "No Syncthing configuration changes needed."
            logger.info(message)
        # --- END RE-ENABLE ---

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
