import os
import subprocess
import logging
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

def load_config():
    """Load configuration from .env file"""
    # Reload dotenv to ensure we get the latest values
    load_dotenv(override=True)
    
    # Run a command to check the actual values loaded
    logger.debug("Loading configuration from .env file with override=True")
    logger.debug(f"RCLONE_OPTIONS from env: {os.getenv('RCLONE_OPTIONS')}")
    
    config = {
        'remote_user': os.getenv('REMOTE_USER'),
        'remote_host': os.getenv('REMOTE_HOST'),
        'remote_port': os.getenv('REMOTE_PORT', '22'),
        'remote_dir': os.getenv('REMOTE_DIR'),
        'local_dir': os.getenv('LOCAL_DIR'),
        'sync_interval': int(os.getenv('SYNC_INTERVAL', '5')),
        'rclone_options': os.getenv('RCLONE_OPTIONS', '--progress --transfers=4 --checkers=8'),
        'use_mounted_volume': os.getenv('USE_MOUNTED_VOLUME', '').lower() == 'true',
        'mounted_volume_path': os.getenv('MOUNTED_VOLUME_PATH', ''),
        'enable_parallel_sync': os.getenv('ENABLE_PARALLEL_SYNC', '').lower() == 'true',
        'parallel_processes': int(os.getenv('PARALLEL_PROCESSES', '4'))
    }
    
    # Validate required config
    required_keys = ['remote_user', 'remote_host', 'remote_dir', 'local_dir']
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

def sync_directory(remote_path, local_base_dir, config):
    """Sync a specific remote directory to local using rclone bisync"""
    # Calculate the relative path from the remote_dir
    base_path = config['mounted_path']
    if remote_path == base_path:
        rel_path = '.'
    else:
        try:
            rel_path = os.path.relpath(remote_path, base_path)
        except ValueError:
            # Handle cases where paths might be on different drives (e.g., Windows)
            # Or if remote_path is not directly under base_path (shouldn't happen with find logic)
            rel_path = os.path.basename(remote_path) # Fallback to just the directory name

    local_path = os.path.join(local_base_dir, rel_path)

    # Ensure the local directory exists
    os.makedirs(local_path, exist_ok=True)

    # Construct rclone bisync command
    rclone_opts_str = config['rclone_options']
    # Split options, remove --bidir if present, then rejoin
    rclone_opts_list = [opt for opt in rclone_opts_str.split() if opt != '--bidir']

    rclone_cmd = [
        'rclone', 'bisync',
        f"{remote_path}/",
        f"{local_path}/"
    ] + rclone_opts_list # Add options from config, excluding --bidir

    # Ensure empty source directories are created on the destination
    rclone_cmd.append('--create-empty-src-dirs')

    # Add common filters (bisync also respects filters)
    # Using /.** to specifically exclude hidden files/dirs in the *root* of the sync path.
    # For node_modules, keep the original exclude.
    rclone_cmd.extend(['--exclude', '/.**', '--exclude', 'node_modules/**'])

    logger.info(f"Performing bisync between {remote_path} <--> {local_path}")
    logger.debug(f"Rclone bisync command: {' '.join(rclone_cmd)}")

    try:
        # Initial bisync attempt
        logger.info(f"Attempting initial bisync for {remote_path} <--> {local_path}")
        result = subprocess.run(
            rclone_cmd,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy() # Ensure rclone uses the current environment
        )
        logger.info(f"Successfully bisynced {remote_path} <--> {local_path} on first attempt.")
        # Log bisync output for debugging potential issues
        if result.stdout:
            logger.debug(f"bisync output:\n{result.stdout}")
        if result.stderr:
            logger.debug(f"bisync stderr:\n{result.stderr}") # bisync often uses stderr for progress/info
        return True
    except subprocess.CalledProcessError as e:
        # bisync has specific exit codes, log them
        logger.error(f"Initial bisync failed for {remote_path} <--> {local_path}. Exit Code: {e.returncode}")
        logger.error(f"Command: {' '.join(e.cmd)}")
        logger.error(f"Stderr: {e.stderr}")
        logger.error(f"Stdout: {e.stdout}")

        # Check if exit code 9 or 7 indicates a resync is needed
        if e.returncode == 9 or e.returncode == 7:
            logger.warning(f"Bisync exited with code {e.returncode}. Attempting --resync...")
            # Construct the resync command
            resync_cmd = rclone_cmd + ['--resync']
            logger.debug(f"Rclone bisync --resync command: {' '.join(resync_cmd)}")

            try:
                # Attempt the resync
                resync_result = subprocess.run(
                    resync_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    env=os.environ.copy()
                )
                logger.info(f"Successfully bisynced {remote_path} <--> {local_path} after --resync.")
                if resync_result.stdout:
                    logger.debug(f"bisync --resync output:\n{resync_result.stdout}")
                if resync_result.stderr:
                    logger.debug(f"bisync --resync stderr:\n{resync_result.stderr}")
                return True
            except subprocess.CalledProcessError as resync_e:
                logger.error(f"Bisync --resync attempt failed for {remote_path} <--> {local_path}. Exit Code: {resync_e.returncode}")
                logger.error(f"Resync Command: {' '.join(resync_e.cmd)}")
                logger.error(f"Resync Stderr: {resync_e.stderr}")
                logger.error(f"Resync Stdout: {resync_e.stdout}")
                return False
            except Exception as resync_ex:
                 logger.error(f"Unexpected error during bisync --resync attempt for {remote_path} <--> {local_path}: {str(resync_ex)}")
                 logger.exception("Resync Traceback:")
                 return False
        else:
            # Error was not exit code 9 or 7, return False without retrying
            logger.error(f"Bisync failed with unrecoverable exit code {e.returncode}. Not attempting resync.")
            return False
    except Exception as e:
        logger.error(f"Unexpected error during initial bisync {remote_path} <--> {local_path}: {str(e)}")
        logger.exception("Traceback:") # Log full traceback for unexpected errors
        return False

def perform_sync():
    """Main function to perform the synchronization using rclone bisync sequentially"""
    try:
        config = load_config()

        # Ensure we're using mounted volume (bisync requires accessible paths)
        if not config.get('is_mounted', False):
            logger.error("Mounted volume not found or not configured. bisync requires direct access.")
            return False, "Mounted volume not available for bisync."

        # Ensure mounted path is accessible
        if not os.path.exists(config['mounted_path']):
            logger.error(f"Mounted path not accessible: {config['mounted_path']}")
            return False, f"Mounted path not accessible: {config['mounted_path']}"

        # List mounted directory contents (for debugging/confirmation)
        # list_remote_directory(config) # Optional: uncomment if needed for debugging

        # Ensure local directory exists
        os.makedirs(config['local_dir'], exist_ok=True)

        # Find directories with .livework files
        # bisync typically works on the root sync pair. The current logic finds
        # directories *containing* .livework and syncs *those* specific directories.
        # This seems reasonable, as it maintains the previous behavior focus.
        livework_dirs = find_livework_dirs(config)

        if not livework_dirs:
            logger.warning("No .livework directories found to sync.")
            # Decision: Do we sync the root mount <-> local_dir if no .livework?
            # For now, sticking to the established .livework logic.
            return False, "No .livework directories found to sync"

        # Sync each directory sequentially using bisync
        logger.info(f"Found {len(livework_dirs)} directories containing .livework to bisync sequentially.")
        successful_syncs = 0
        total_dirs = len(livework_dirs)

        for i, remote_dir in enumerate(livework_dirs):
            logger.info(f"--- Starting bisync for directory {i+1}/{total_dirs}: {remote_dir} ---")
            if sync_directory(remote_dir, config['local_dir'], config):
                successful_syncs += 1
            else:
                # Log failure for this specific directory but continue with others
                logger.warning(f"Bisync failed for directory: {remote_dir}. Continuing with next.")
            logger.info(f"--- Finished bisync for directory {i+1}/{total_dirs}: {remote_dir} ---")


        logger.info(f"Sequential bisync completed. {successful_syncs}/{total_dirs} directories attempted.")
        # Report overall success only if all directories succeeded.
        if successful_syncs == total_dirs:
             return True, f"Bisynced {successful_syncs}/{total_dirs} directories successfully."
        else:
             return False, f"Bisync completed with {total_dirs - successful_syncs} failures out of {total_dirs} directories."

    except ValueError as e: # Catch config loading errors
        logger.error(f"Configuration error during sync process: {str(e)}")
        return False, f"Configuration error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error during perform_sync: {str(e)}")
        logger.exception("Traceback:") # Log full traceback
        return False, f"Sync failed due to unexpected error: {str(e)}"
