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
        # Add progress flags, itemize changes, and --no-i-r
        # -i (--itemize-changes) gives per-file output
        # --info=progress2 gives machine-readable progress
        # --no-i-r recommended with progress2
        rsync_opts_list = shlex.split(rsync_opts_str) + ['--info=progress2', '--no-i-r', '-i']
    except ImportError:
        # Fallback for environments without shlex
        rsync_opts_list = rsync_opts_str.split() + ['--info=progress2', '--no-i-r', '-i']

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
    if signal_emitter:
        try:
            # Emit signal directly (must be called from the main thread or use Qt's queued connections)
            # Since this runs in a worker process, direct emit might not work as expected
            # unless the emitter is designed for cross-process signaling or handled carefully.
            # For now, assuming it's handled correctly by the caller's setup (e.g., queued connection).
            signal_emitter.sync_progress_update.emit({'type': 'start', 'project': project_name, 'path': remote_path})
        except Exception as emit_err:
            logger.error(f"Failed to emit start signal for {project_name}: {emit_err}")
    # --- End Report Start ---

    success = False # Default to failure
    synced_files = [] # List to store transferred files
    error_message = "" # Store specific error message
    process = None
    try:
        # Use Popen to stream output
        logger.debug(f"Starting Popen for: {' '.join(rsync_cmd)}")
        process = subprocess.Popen(
            rsync_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Capture stderr too
            text=True,
            bufsize=1,  # Line buffered
            env=os.environ.copy()
        )

        # Regexes for parsing output
        # Progress: "         32768   0% ..." or "   131072000  99% ..."
        progress_regex = re.compile(r'\s+(\d+)%\s+')
        # Itemize changes: ">f+++++++++ filename" (sent), "<f.st...... filename" (deleted), ".d..t...... dirname/" (dir properties)
        # We only care about sent/updated files (lines starting with >f)
        itemize_regex = re.compile(r'^>f[+.]') # Matches files being sent or updated locally
        last_reported_percentage = -1

        # Read stdout line by line
        logger.debug(f"Reading stdout for {project_name}...")
        if process.stdout:
            while True:
                line = process.stdout.readline()
                if not line:
                    # If readline returns empty, check if the process has finished.
                    if process.poll() is not None:
                        logger.debug(f"End of stdout stream and process terminated for {project_name}.")
                        break # End of stream and process finished
                    else:
                        # Process still running, but no output right now, wait briefly
                        time.sleep(0.05)
                        continue

                line_strip = line.strip()
                if not line_strip: # Skip empty lines
                    continue

                logger.debug(f"rsync raw ({project_name}): {line_strip}") # Log raw output for debugging

                # Check for progress update
                progress_match = progress_regex.search(line)
                if progress_match:
                    percentage = int(progress_match.group(1))
                    # Only report if percentage changes to avoid flooding the emitter
                    if percentage != last_reported_percentage:
                        logger.debug(f"Parsed progress for {project_name}: {percentage}%")
                        if signal_emitter:
                            try:
                                signal_emitter.sync_progress_update.emit({
                                    'type': 'progress',
                                    'project': project_name,
                                    'path': remote_path,
                                    'percentage': percentage
                                })
                                last_reported_percentage = percentage
                            except Exception as emit_err:
                                logger.error(f"Failed to emit progress signal for {project_name}: {emit_err}")
                    continue # Progress lines don't contain itemize info

                # Check for itemized change (file transfer)
                # Example: >f+++++++++ my_document.txt
                if itemize_regex.match(line):
                    # Extract filename (part after the 11-char code and space)
                    filename = line[12:].strip()
                    if filename:
                        synced_files.append(filename)
                        logger.debug(f"Tracked synced file for {project_name}: {filename}")

        # Wait for the process to finish and get the exit code and stderr
        logger.debug(f"Waiting for rsync process to complete for {project_name}...")
        stdout_final, stderr_final = process.communicate() # Get any remaining output/errors
        return_code = process.returncode
        logger.debug(f"Rsync process for {project_name} finished with code: {return_code}")

        # Log any final stderr output
        if stderr_final:
            stderr_final_strip = stderr_final.strip()
            logger.debug(f"rsync final stderr for {remote_path}:\n{stderr_final_strip}")
            # Store stderr as potential error message, unless it's just stats
            # (rsync often prints stats to stderr even on success)
            if return_code != 0 or "total size is" not in stderr_final_strip:
                 error_message = stderr_final_strip

        if return_code == 0:
            logger.info(f"Successfully synced {remote_path} -> {local_path}")
            success = True
        else:
            logger.error(f"Rsync failed for {remote_path} -> {local_path}. Exit Code: {return_code}")
            logger.error(f"Command: {' '.join(rsync_cmd)}") # Log the command used
            # Use captured stderr if available, otherwise provide generic message
            if not error_message:
                 error_message = f"Rsync failed with exit code {return_code}."
            logger.error(f"Error details: {error_message}")
            success = False

    except Exception as e:
        logger.error(f"Unexpected error during rsync {remote_path} -> {local_path}: {str(e)}")
        logger.exception("Traceback:")
        success = False
        error_message = f"Unexpected Python error: {str(e)}" # Store Python exception message
        # Ensure process is terminated if it's still running after an exception
        if process and process.poll() is None:
            try:
                logger.warning(f"Terminating runaway rsync process for {project_name} due to exception.")
                process.terminate()
                process.wait(timeout=5) # Wait a bit for termination
            except:
                logger.warning(f"Force killing runaway rsync process for {project_name}.")
                process.kill() # Force kill if terminate fails
    finally:
        # --- Report End ---
        if signal_emitter:
            try:
                # Emit end signal
                signal_emitter.sync_progress_update.emit({'type': 'end', 'project': project_name, 'path': remote_path, 'success': success, 'error': error_message if not success else None})
            except Exception as emit_err:
                logger.error(f"Failed to emit end signal for {project_name}: {emit_err}")
        # --- End Report End ---

    # Return detailed result dictionary
    result_data = {'success': success}
    if success:
        result_data['synced_files'] = synced_files
    else:
        result_data['error'] = error_message
        # TODO: Add more robust lock file detection here if needed based on error_message
        # Example basic check (might need refinement):
        # if "lock file" in error_message.lower():
        #    result_data['error_type'] = 'lock_file'
        #    result_data['path'] = remote_path # Assuming path needed for lock removal

    return (remote_path, result_data) # Return path and result dictionary

def perform_sync(signal_emitter=None):
    """
    Main function to perform synchronization using rsync, potentially in parallel.

    Args:
        signal_emitter (SyncSignalEmitter, optional): Emitter for sending progress updates via signals.

    Returns:
        dict: A dictionary mapping remote directory paths to their sync result data.
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
                                signal_emitter=signal_emitter) # Pass the signal_emitter here

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
