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
 
def load_config(dotenv_path=None):
    """
    Load configuration from .env file.
    Prioritizes the file specified by dotenv_path if provided.
    """
    if dotenv_path and os.path.exists(dotenv_path):
        logger.info(f"Loading configuration from specified path: {dotenv_path}")
        load_dotenv(dotenv_path=dotenv_path, override=True)
    else:
        # Fallback to default behavior (searching current/parent dirs) if path not provided or doesn't exist
        # This might be useful for development environments, but less so for the packaged app.
        logger.warning(f"Specified dotenv_path '{dotenv_path}' not found or not provided. Falling back to default load_dotenv behavior.")
        load_dotenv(override=True) # Original call

    logger.debug(f"Attempting to load configuration values after load_dotenv(override=True, path='{dotenv_path}')")
    logger.debug(f"RSYNC_OPTIONS from env: {os.getenv('RSYNC_OPTIONS')}") # Changed from RCLONE_OPTIONS

    config = {
        'remote_user': os.getenv('REMOTE_USER'),
        'remote_host': os.getenv('REMOTE_HOST'),
        'remote_port': os.getenv('REMOTE_PORT', '22'),
        'remote_dir': os.getenv('REMOTE_DIR'),
        'local_dir': os.getenv('LOCAL_DIR'),
        'sync_interval': int(os.getenv('SYNC_INTERVAL', '5')), # Interval for checking/updating Syncthing config
        'use_mounted_volume': os.getenv('USE_MOUNTED_VOLUME', '').lower() == 'true',
        'mounted_volume_path': os.getenv('MOUNTED_VOLUME_PATH', ''),
        # --- Syncthing Specific Config ---
        'remote_syncthing_device_id': os.getenv('REMOTE_SYNCTHING_DEVICE_ID'),
        'syncthing_api_key': os.getenv('SYNCTHING_API_KEY'), # Optional, can be auto-retrieved
        'syncthing_listen_address': os.getenv('SYNCTHING_LISTEN_ADDRESS', '127.0.0.1:8385'), # Default local daemon API
        # --- File Watching Config ---
        'watch_local_files': os.getenv('WATCH_LOCAL_FILES', 'true').lower() == 'true',
        'watch_delay_seconds': int(os.getenv('WATCH_DELAY_SECONDS', '2')),
        # --- Start at Login ---
        'start_at_login': os.getenv('START_AT_LOGIN', 'false').lower() == 'true',
    }

    # Validate required config
    required_keys = ['local_dir', 'remote_syncthing_device_id'] # Local dir and remote ID are essential
    if not config['use_mounted_volume']:
        # If not using mounted volume, SSH details are needed *only* for finding .livework files
        required_keys.extend(['remote_user', 'remote_host', 'remote_dir'])
        logger.info("SSH details required for discovering .livework files remotely.")
    elif not config['mounted_volume_path']:
         # If using mounted volume for discovery, the path must be set
         required_keys.append('mounted_volume_path')
         logger.info("Mounted volume path required for discovering .livework files locally.")

    missing_keys = [key for key in required_keys if not config.get(key)]
    if missing_keys:
        raise ValueError(f"Missing required configuration: {', '.join(missing_keys)}")
    
    # Ensure remote_dir is properly formatted for shell commands
    # Remove any extra quotes that might have been included in the env file
    if config['remote_dir'].startswith('"') and config['remote_dir'].endswith('"'):
        config['remote_dir'] = config['remote_dir'][1:-1]
    elif config['remote_dir'].startswith("'") and config['remote_dir'].endswith("'"):
        config['remote_dir'] = config['remote_dir'][1:-1]
    
    # Check for mounted volume usage
    config['is_mounted'] = False
    
    # First priority: Use explicitly specified mounted volume path if provided
    if config['mounted_volume_path'] and config['use_mounted_volume']:
        if os.path.exists(config['mounted_volume_path']):
            logger.info(f"Using explicitly configured mounted volume: {config['mounted_volume_path']}")
            config['mounted_path'] = config['mounted_volume_path']
            config['is_mounted'] = True
        else:
            logger.warning(f"Configured MOUNTED_VOLUME_PATH not found: {config['mounted_volume_path']}")
            logger.warning("Will try auto-detection or fall back to SSH")
    
    # Second priority: Try auto-detection if mounted volume is enabled but path not specified or not found
    if not config['is_mounted'] and config['use_mounted_volume']:
        # Convert from remote path format (with escape characters) to local path format (without escapes)
        raw_remote_dir = config['remote_dir'].replace('\\', '')  # Remove escape characters
        mounted_path = raw_remote_dir.replace('volume1', 'Volumes')
        
        if os.path.exists(f"/{mounted_path}"):
            logger.info(f"Using auto-detected mounted volume at /{mounted_path}")
            config['mounted_path'] = f"/{mounted_path}"
            config['is_mounted'] = True
        else:
            logger.warning(f"Could not auto-detect mounted volume at /{mounted_path}")
            logger.debug(f"Path checked: /{mounted_path}")
    
    # If not using mounted volume, log that we're using SSH
    if not config['is_mounted']:
        logger.info("Not using mounted volume, will connect via SSH")
    
    logger.info("Configuration loaded:")
    logger.info(f"  Remote: {config['remote_user']}@{config['remote_host']}:{config['remote_port']}")
    logger.info(f"  Remote Directory: {config['remote_dir']}")
    logger.info(f"  Local Directory: {config['local_dir']}")
    logger.info(f"  Sync Interval: {config['sync_interval']} minutes")
    logger.info(f"  Using Mounted Volume: {config['is_mounted']}")
    if config['is_mounted']:
        logger.info(f"  Mounted Volume Path: {config['mounted_path']}")
    
    # Log Syncthing specific config
    logger.info(f"  Remote Syncthing Device ID: {config['remote_syncthing_device_id']}")
    logger.info(f"  Local Syncthing API Address: {config['syncthing_listen_address']}")
    logger.info(f"  Local File Watching: {config['watch_local_files']}")
    if config['watch_local_files']:
        logger.info(f"  File Watch Delay: {config['watch_delay_seconds']} seconds")
    logger.info(f"  Start at Login: {config['start_at_login']}")

    return config

# Removed test_remote_connection (SSH specific, only used for initial check, not core sync)

def find_livework_dirs(config):
    """Find directories with .livework files on the remote server or mounted volume"""
    logger.info("Scanning for .livework files")
    
    livework_dirs = []
    
    # If the volume is mounted locally, search directly on the filesystem
    if config.get('is_mounted', False):
        mounted_path = config['mounted_path']
        logger.info(f"Searching for .livework files in mounted volume: {mounted_path}")
        
        try:
            # Log the top-level directory contents for debugging
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
            
            logger.info(f"Found {len(livework_dirs)} directories with .livework files")
            return livework_dirs
            
        except Exception as e:
            logger.error(f"Error finding .livework directories in mounted volume: {str(e)}")
            return []
    
    # Otherwise, use SSH to find the directories
    else:
        logger.info("Scanning for .livework files on remote server")
        
        # Use a more robust command that properly handles paths with spaces and special characters
        # The command first changes to the remote directory, then finds .livework files
        # relative to that location to avoid path issues
        # Use single quotes around the path for better shell escaping
        remote_dir = config['remote_dir'].replace('"', '\\"')
        
        cmd = [
            'ssh',
            f"{config['remote_user']}@{config['remote_host']}",
            '-p', config['remote_port'],
            f"cd '{remote_dir}' && find . -name '.livework' -type f | xargs -I{{}} dirname {{}}"
        ]
        
        logger.debug(f"Find command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Process relative paths (they'll start with ./)
            for line in result.stdout.splitlines():
                if line.strip():
                    # Convert relative path to absolute
                    rel_path = line.strip()
                    abs_path = os.path.normpath(os.path.join(config['remote_dir'], rel_path))
                    livework_dirs.append(abs_path)
                    logger.info(f"Found .livework in: {abs_path}")
                    
            logger.info(f"Found {len(livework_dirs)} directories with .livework files")
            return livework_dirs
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Error finding .livework directories: {str(e)}")
            logger.error(f"Error output: {e.stderr}")
            return []

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
        config = load_config(dotenv_path=user_env_path)
        if not config:
            raise ValueError("Failed to load TurboSync configuration.")

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

        # Map remote paths to desired local paths and folder IDs
        desired_folders = {} # {folder_id: {'local_path': '/path/to/local', 'remote_path': '/path/to/remote'}}
        base_remote_or_mount = config.get('mounted_path') if config['is_mounted'] else config['remote_dir']

        for remote_path in livework_remote_paths:
            # Derive local path relative to the local_base_dir
            if remote_path == base_remote_or_mount:
                rel_path = '.' # Sync the base directory itself if it has .livework
            else:
                try:
                    rel_path = os.path.relpath(remote_path, base_remote_or_mount)
                except ValueError:
                    # Fallback if paths are on different drives (e.g., Windows) or other issues
                    rel_path = os.path.basename(remote_path)
                    logger.warning(f"Could not determine relative path for '{remote_path}' relative to '{base_remote_or_mount}'. Using basename '{rel_path}'.")

            local_path = os.path.normpath(os.path.join(local_base_dir, rel_path))
            # Create a reasonably unique folder ID (e.g., based on relative path)
            # Replace path separators with underscores for Syncthing ID compatibility
            folder_id = rel_path.replace(os.path.sep, '_').replace(' ', '_').replace('.', '_livework')
            if not folder_id or folder_id == '_livework': # Handle base directory case
                 folder_id = os.path.basename(local_base_dir) + '_livework_base'

            # Ensure local directory exists (Syncthing might need it)
            os.makedirs(local_path, exist_ok=True)

            desired_folders[folder_id] = {'local_path': local_path, 'remote_path': remote_path}
            logger.debug(f"Desired folder: ID='{folder_id}', Local='{local_path}', Remote='{remote_path}'")

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
