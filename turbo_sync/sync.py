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
    logger.debug(f"RCLONE_OPTIONS from env: {os.getenv('RCLONE_OPTIONS')}")
    
    config = {
        'remote_user': os.getenv('REMOTE_USER'),
        'remote_host': os.getenv('REMOTE_HOST'),
        'remote_port': os.getenv('REMOTE_PORT', '22'),
        'remote_dir': os.getenv('REMOTE_DIR'),
        'local_dir': os.getenv('LOCAL_DIR'),
        'sync_interval': int(os.getenv('SYNC_INTERVAL', '5')),
        'rsync_options': os.getenv('RSYNC_OPTIONS', '-avz --delete --progress'), # Changed from rclone_options
        'use_mounted_volume': os.getenv('USE_MOUNTED_VOLUME', '').lower() == 'true',
        'mounted_volume_path': os.getenv('MOUNTED_VOLUME_PATH', ''),
        # 'enable_parallel_sync' is removed, parallelization handled by ProcessPoolExecutor
        'parallel_processes': int(os.getenv('PARALLEL_PROCESSES', '4'))
    }

    # Validate required config for SSH mode, less strict for mounted mode
    required_keys = ['local_dir']
    if not config['use_mounted_volume']:
        required_keys.extend(['remote_user', 'remote_host', 'remote_dir'])
    elif not config['mounted_volume_path']:
         # If using mounted volume, the path must be set
         required_keys.append('mounted_volume_path')
    for key in required_keys:
        if not config[key]:
            raise ValueError(f"Missing required configuration: {key}")
    
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
    
    return config

def test_remote_connection(config):
    """Test SSH connection to remote server"""
    logger.info("Testing remote connection...")
    cmd = [
        'ssh',
        f"{config['remote_user']}@{config['remote_host']}",
        '-p', config['remote_port'],
        'echo "Connection successful"'
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        logger.info("Remote connection successful")
        return True
    except subprocess.TimeoutExpired:
        logger.error("Remote connection timed out")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Remote connection failed: {e.stderr}")
        return False

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

def list_remote_directory(config):
    """List contents of remote directory or mounted volume"""
    if config.get('is_mounted', False):
        mounted_path = config['mounted_path']
        logger.info(f"Listing contents of mounted directory: {mounted_path}")
        
        try:
            # List the directory contents
            entries = os.listdir(mounted_path)
            logger.info("Mounted directory contents:")
            for entry in entries:
                logger.info(f"  {entry}")
            return True
        except Exception as e:
            logger.error(f"Error listing mounted directory: {str(e)}")
            return False
    else:
        logger.info(f"Listing contents of remote directory: {config['remote_dir']}")
        
        # Use single quotes around the path for better shell escaping
        remote_dir = config['remote_dir'].replace('"', '\\"')
        
        cmd = [
            'ssh',
            f"{config['remote_user']}@{config['remote_host']}",
            '-p', config['remote_port'],
            f"ls -la '{remote_dir}'"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info("Remote directory contents:")
            logger.info(result.stdout)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error listing remote directory: {e.stderr}")
            return False

def sync_directory(remote_dir_info, local_base_dir, config, progress_queue=None):
    """
    Sync a specific remote directory to a local directory using rsync.

    Args:
        remote_dir_info (tuple): A tuple containing (index, remote_path).
        local_base_dir (str): The base local directory to sync into.
        config (dict): The loaded configuration dictionary.
        progress_queue (multiprocessing.Queue, optional): Queue to send progress updates.

    Returns:
        tuple: (remote_path, success_flag) where success_flag is True or False.
    """
    index, remote_path = remote_dir_info
    project_name = os.path.basename(remote_path) # Get project name for reporting
    rsync_executable = shutil.which('rsync') or 'rsync' # Find rsync or default

    # Calculate the relative path from the base remote directory or mounted path
    if config['is_mounted']:
        base_path = config['mounted_path']
    else:
        base_path = config['remote_dir'] # Use the configured remote base for SSH

    if remote_path == base_path:
        rel_path = '.'
    else:
        try:
            # Use relpath carefully, ensuring both paths are absolute or relative consistently
            # For SSH, remote_path is absolute, base_path might need adjustment if not absolute
            # For mounted, both should be absolute paths
            rel_path = os.path.relpath(remote_path, base_path)
        except ValueError:
            rel_path = os.path.basename(remote_path) # Fallback

    local_path = os.path.join(local_base_dir, rel_path)

    # Ensure the local target directory exists
    os.makedirs(local_path, exist_ok=True)

    # Construct rsync command
    rsync_opts_str = config['rsync_options']
    # Use shlex to split options correctly, handling quotes
    try:
        import shlex
        rsync_opts_list = shlex.split(rsync_opts_str)
    except ImportError:
        rsync_opts_list = rsync_opts_str.split() # Fallback for environments without shlex

    rsync_cmd = [rsync_executable] + rsync_opts_list

    # Define source and destination
    # Ensure trailing slashes for directory content sync
    dest = local_path.rstrip('/') + '/'

    if config['is_mounted']:
        source = remote_path.rstrip('/') + '/'
        logger.info(f"Performing rsync (mounted): {source} -> {dest}")
    else: # SSH mode
        # Escape spaces and special characters for SSH path
        # Using shlex.quote is safer if available
        try:
            import shlex
            escaped_remote_path = shlex.quote(remote_path.rstrip('/'))
        except ImportError:
            # Basic escaping for spaces if shlex not available
            escaped_remote_path = remote_path.replace(' ', '\\ ')

        source = f"{config['remote_user']}@{config['remote_host']}:{escaped_remote_path}/"
        # Add SSH options (port)
        rsync_cmd.extend(['-e', f"ssh -p {config['remote_port']}"])
        logger.info(f"Performing rsync (SSH): {source} -> {dest}")

    rsync_cmd.extend([source, dest])

    logger.debug(f"Rsync command for '{remote_path}': {' '.join(rsync_cmd)}")

    # --- Report Start ---
    if progress_queue:
        try:
            progress_queue.put({'type': 'start', 'project': project_name, 'path': remote_path})
        except Exception as q_err:
            logger.error(f"Failed to put start message on queue for {project_name}: {q_err}")
    # --- End Report Start ---

    success = False # Default to failure
    try:
        # Run rsync
        result = subprocess.run(
            rsync_cmd,
            capture_output=True,
            text=True,
            check=True, # Raise exception on non-zero exit code
            env=os.environ.copy()
        )
        logger.info(f"Successfully synced {remote_path} -> {local_path}")
        if result.stdout:
            logger.debug(f"rsync output for {remote_path}:\n{result.stdout}")
        if result.stderr:
            # rsync often uses stderr for stats/errors, log it
            logger.debug(f"rsync stderr for {remote_path}:\n{result.stderr}")
        success = True
    except subprocess.CalledProcessError as e:
        logger.error(f"Rsync failed for {remote_path} -> {local_path}. Exit Code: {e.returncode}")
        logger.error(f"Command: {' '.join(e.cmd)}")
        logger.error(f"Stderr: {e.stderr}")
        logger.error(f"Stdout: {e.stdout}")
        success = False
    except Exception as e:
        logger.error(f"Unexpected error during rsync {remote_path} -> {local_path}: {str(e)}")
        logger.exception("Traceback:")
        success = False
    finally:
        # --- Report End ---
        if progress_queue:
            try:
                progress_queue.put({'type': 'end', 'project': project_name, 'path': remote_path, 'success': success})
            except Exception as q_err:
                logger.error(f"Failed to put end message on queue for {project_name}: {q_err}")
        # --- End Report End ---

    return (remote_path, success) # Return path and final success status

def perform_sync(progress_queue=None):
    """
    Main function to perform synchronization using rsync, potentially in parallel.

    Args:
        progress_queue (multiprocessing.Queue, optional): Queue for sending progress updates.

    Returns:
        dict: A dictionary mapping remote directory paths to their sync status (True/False).
              Returns None if a configuration error or major exception occurs.
    """
    import shutil # Ensure shutil is imported for which()
    try:
        # Use the user-specific .env path consistently
        user_env_path = os.path.join(os.path.expanduser(f'~/Library/Application Support/TurboSync'), '.env')
        config = load_config(dotenv_path=user_env_path)

        # Check if rsync executable exists
        rsync_path = shutil.which('rsync')
        if not rsync_path:
             # Try common paths if not in PATH (especially relevant in bundled app)
             common_paths = ['/usr/bin/rsync']
             for p in common_paths:
                 if os.path.exists(p):
                     rsync_path = p
                     break
        if not rsync_path:
            logger.error("rsync executable not found in PATH or common locations (/usr/bin/rsync). Please install rsync.")
            # Consider notifying the user via menubar if possible here
            return None

        logger.info(f"Using rsync executable at: {rsync_path}")


        # Validate connection or mounted path based on mode
        if config['is_mounted']:
            if not os.path.exists(config['mounted_path']):
                logger.error(f"Mounted path not accessible: {config['mounted_path']}")
                return None
            logger.info(f"Confirmed mounted path exists: {config['mounted_path']}")
        else: # SSH mode
            if not test_remote_connection(config): # Keep connection test for SSH
                 logger.error("Remote SSH connection test failed. Cannot proceed with sync.")
                 return None

        # Ensure local directory exists
        os.makedirs(config['local_dir'], exist_ok=True)

        # Find directories with .livework files
        livework_dirs = find_livework_dirs(config)

        if not livework_dirs:
            logger.warning("No .livework directories found to sync.")
            return {} # Return empty dict, no syncs attempted

        logger.info(f"Found {len(livework_dirs)} directories containing .livework to sync.")

        # Use ProcessPoolExecutor for parallel execution
        max_workers = config.get('parallel_processes', 1) # Default to 1 if not set
        logger.info(f"Starting parallel sync with up to {max_workers} processes...")
        sync_results = {}
        tasks = [(i, dir_path) for i, dir_path in enumerate(livework_dirs)]

        # Use 'spawn' context if available for better compatibility across platforms
        mp_context = multiprocessing.get_context('spawn')
        with ProcessPoolExecutor(max_workers=max_workers, mp_context=mp_context) as executor:
            # Map sync_directory function over the directories
            # Pass necessary arguments using functools.partial, including the queue
            from functools import partial
            sync_func = partial(sync_directory,
                                local_base_dir=config['local_dir'],
                                config=config,
                                progress_queue=progress_queue) # Pass the queue here

            # Execute tasks and gather results as they complete
            results_iterator = executor.map(sync_func, tasks)

            for remote_path, result_data in results_iterator:
                sync_results[remote_path] = result_data # Store the whole dict
                status = "succeeded" if result_data['success'] else "failed"
                logger.info(f"Sync task for {remote_path} {status}.")


        successful_syncs = sum(1 for res in sync_results.values() if res['success'])
        total_dirs = len(livework_dirs)
        logger.info(f"Parallel sync completed. {successful_syncs}/{total_dirs} directories synced successfully.")
        return sync_results

    except ValueError as e: # Catch config loading errors
        logger.error(f"Configuration error during sync process: {str(e)}")
        return None # Indicate general failure
    except Exception as e:
        logger.error(f"Unexpected error during perform_sync: {str(e)}")
        logger.exception("Traceback:") # Log full traceback
        return None # Indicate general failure
