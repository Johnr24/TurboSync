import os
import sys
import functools # Import functools for partial
import time
import threading
import logging
import shutil # Import shutil
import rumps
import subprocess # Added for AppleScript execution
# Removed explicit component imports for rumps 0.4.0
# from rumps import separator, Text, EditText, Checkbox, Window, MenuItem, App, notification, quit_application
import schedule
from dotenv import load_dotenv, set_key, dotenv_values # Added set_key, dotenv_values
from collections import OrderedDict # To maintain setting order

# --- PySide6 Imports (Removed - Now handled in settings_dialog.py) ---
# from PySide6.QtWidgets import QApplication, QDialog, ...
# from PySide6.QtCore import Qt, Slot

from turbo_sync.sync import perform_sync, load_config, find_livework_dirs # Absolute import, added find_livework_dirs
from turbo_sync.watcher import FileWatcher, is_fswatch_available, get_fswatch_config # Absolute import
import multiprocessing # Import multiprocessing for Queue and Manager
import textwrap # For formatting long messages
from turbo_sync.utils import get_resource_path # Import from utils
# --- Import the Settings Dialog logic ---
from turbo_sync.settings_dialog import launch_pyside_settings_dialog # Import the launcher function

# Define user-specific config path (consistent with main.py)
APP_NAME = "TurboSync"
USER_CONFIG_DIR = os.path.expanduser(f'~/Library/Application Support/{APP_NAME}')
USER_ENV_PATH = os.path.join(USER_CONFIG_DIR, '.env')

class TurboSyncMenuBar(rumps.App): # Reverted to rumps.App
    def __init__(self):
        logging.info("Initializing TurboSyncMenuBar")

        # Determine the icon path using the helper function
        icon_path = get_resource_path("icon.png")
        if not icon_path or not os.path.exists(icon_path):
             logging.error(f"Icon not found at expected path: {icon_path}. Trying fallback.")
             # Attempt to create a fallback icon if the primary one is missing
             icon_path = self.create_fallback_icon()
             if not icon_path:
                 logging.error("Fallback icon creation failed. Using default rumps icon.")

        # Initialize the app with the icon if found/created
        try:
            logging.info(f"Initializing rumps.App with icon_path: {icon_path}")
            super(TurboSyncMenuBar, self).__init__(
                "TurboSync",
                icon=icon_path
                # Removed quit_button=None - Rely on default
            )
            logging.info("rumps.App initialization successful")
        except Exception as e:
            logging.error(f"Failed to initialize rumps.App: {e}")
            # Continue anyway with default icon
            super(TurboSyncMenuBar, self).__init__(
                "TurboSync"
                # Removed quit_button=None - Rely on default
            )
            logging.info("Initialized rumps.App with default icon")

        logging.debug("Setting up menu items")
        # State variables (define before menu items that might use them)
        self.syncing = False
        self.sync_thread = None
        # self.status_item = None # Defined below
        self.last_sync_status = "Never synced"
        self.file_watcher = None
        self.watch_enabled = False # Will be updated by setup_file_watcher
        self.last_sync_results = {} # Store detailed results {path: {'success': bool, 'synced_files': [], 'error': 'msg', 'error_type': 'optional_str'}}
        self.active_sync_progress = {} # Store current progress {path: percentage}
        # Use Manager().Queue() for inter-process communication with ProcessPoolExecutor
        self.manager = multiprocessing.Manager()
        self.progress_queue = self.manager.Queue() # Queue for sync progress
        self.progress_timer = None # Timer to check the queue
        self.status_panel_window = None # Reference to the status panel window

        # --- Define Items Needing State Management First ---
        self.status_item = rumps.MenuItem(f"Status: {self.last_sync_status}")
        self.watch_toggle = rumps.MenuItem("Enable File Watching") # Title matches decorator
       # Create the main menu item that will hold the submenu
       self.synced_projects_item = rumps.MenuItem("Synced Projects")

       # --- Define Complete Menu Structure ---
       self.status_panel_item = rumps.MenuItem("Show Sync Status") # New item
       # Construct the list with MenuItem objects included directly
       menu_items = [
           self.status_item,       # Insert the MenuItem object
           "Sync Now",
           self.status_panel_item, # Add the new item here
           "View Logs",
           self.synced_projects_item, # Add the new item here
           None,                   # Separator
           self.watch_toggle,      # Insert the MenuItem object
            "Settings",
            None,                   # Separator
            # Quit item added by rumps automatically
        ]
        self.menu = menu_items      # Assign the final list to self.menu

        # Add initial placeholder to the submenu
        self.synced_projects_item.add(rumps.MenuItem("Loading..."))

        # Load configuration
        try:
            logging.debug(f"Loading configuration using path: {USER_ENV_PATH}")
            self.config = load_config(dotenv_path=USER_ENV_PATH) # Pass the path
            if not self.config: # load_config might return None or raise error handled below
                raise ValueError("load_config failed to return a valid configuration.")
            logging.info(f"Configuration loaded, sync interval: {self.config['sync_interval']} minutes")
            schedule.every(self.config['sync_interval']).minutes.do(self.scheduled_sync)

            # Update the synced projects list now that config is loaded
            self.update_synced_projects_list()

            # Set up file watcher if enabled
            self.setup_file_watcher()

        except Exception as e:
            logging.error(f"Error loading configuration: {e}")
            rumps.notification( # Reverted to rumps.notification
                "TurboSync Configuration Error",
                "Error loading configuration",
                f"Please check your .env file: {str(e)}",
                sound=True
            )
            self.synced_projects_item.clear() # Clear existing items (like "Loading...")
            self.synced_projects_item.add(rumps.MenuItem("Config Error"))
            self.status_item.title = f"Status: Configuration Error"

    def create_fallback_icon(self):
        """Creates a simple fallback icon if the main one is missing."""
        logging.warning("Attempting to create a fallback icon.")
        # Use a temporary directory for the fallback icon
        temp_icon_path = os.path.join(os.path.expanduser("~/Library/Logs/TurboSync"), "fallback_icon.png")
        try:
            os.makedirs(os.path.dirname(temp_icon_path), exist_ok=True)
            # Try to create a simple icon using PIL if available
            # Check if PIL is available
            try:
                from PIL import Image, ImageDraw
                # Create a smaller 64x64 image for the menubar
                img = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                # Draw a simple colored circle (e.g., blue with white center)
                draw.ellipse([(4, 4), (60, 60)], fill=(0, 120, 255, 255)) # Blue outer
                draw.ellipse([(16, 16), (48, 48)], fill=(255, 255, 255, 255)) # White inner
                img.save(temp_icon_path)
                logging.info(f"Created fallback icon using PIL at {temp_icon_path}")
                return temp_icon_path
            except ImportError:
                logging.error("PIL not found, cannot create fallback icon.")
                return None
        except Exception as e:
            logging.error(f"Failed to create fallback icon: {e}")
            return None

    def setup_file_watcher(self):
        """Set up the file watcher based on config"""
        logging.debug("Setting up file watcher")
        fswatch_config = get_fswatch_config()
        self.watch_enabled = fswatch_config['watch_enabled']

        # Update menu item state
        self.watch_toggle.state = self.watch_enabled

        # Only start watcher if fswatch is available and enabled
        if self.watch_enabled and is_fswatch_available():
            try:
                logging.info(f"Starting file watcher for: {fswatch_config['local_dir']}")
                self.file_watcher = FileWatcher(
                    fswatch_config['local_dir'],
                    self.on_files_changed,
                    fswatch_config['watch_delay']
                )
                if self.file_watcher.start():
                    logging.info("File watcher started successfully")
                    rumps.notification( # Reverted to rumps.notification
                        "TurboSync",
                        "File Watcher Started",
                        f"Watching {fswatch_config['local_dir']} for changes",
                        sound=False
                    )
                else:
                    logging.error("Failed to start file watcher")
            except Exception as e:
                logging.error(f"Error starting file watcher: {e}")
                rumps.notification( # Reverted to rumps.notification
                    "TurboSync",
                    "File Watcher Error",
                    f"Could not start file watcher: {str(e)}",
                    sound=True
                )
                self.watch_toggle.state = False
                self.watch_enabled = False
        elif self.watch_enabled and not is_fswatch_available():
            logging.warning("fswatch not available but file watching is enabled")
            rumps.notification( # Reverted to rumps.notification
                "TurboSync",
                "fswatch Not Found",
                "Please install fswatch to enable file watching: brew install fswatch",
                sound=True
            )
            self.watch_toggle.state = False
            self.watch_enabled = False
        else:
            logging.debug("File watching is disabled")

    def on_files_changed(self):
        """Callback for when files change"""
        logging.debug("File changes detected")
        if not self.syncing:
            logging.info("Starting sync due to file changes")
            rumps.notification( # Reverted to rumps.notification
                "TurboSync",
                "File Changes Detected",
                "Starting sync due to local file changes",
                sound=False
            )
            self.sync_now(None)

    @rumps.clicked("Enable File Watching") # Keep decorator
    def toggle_file_watching(self, sender):
        """Toggle file watching on/off"""
        # IMPORTANT: Now 'sender' will be the self.watch_toggle MenuItem object
        logging.debug(f"Toggle file watching: current state is {self.watch_toggle.state}") # Use self.watch_toggle
        # Use self.watch_toggle for state checks and updates
        if self.watch_toggle.state:  # Currently enabled, disable it
            logging.info("Disabling file watching")
            self.watch_toggle.state = False # Update the correct item's state
            self.watch_enabled = False

            if self.file_watcher:
                 # Indented block for the correct if statement above
                 logging.debug("Stopping file watcher")
                 self.file_watcher.stop()
                 self.file_watcher = None
            # The rest of the logic for disabling continues below

            rumps.notification( # Reverted to rumps.notification
                "TurboSync",
                "File Watching Disabled",
                "Will no longer sync on file changes",
                sound=False
            )
        else:  # Currently disabled, enable it
            if not is_fswatch_available():
                logging.warning("Cannot enable file watching, fswatch not available")
                rumps.notification( # Reverted to rumps.notification
                    "TurboSync",
                    "fswatch Not Found",
                    "Please install fswatch: brew install fswatch",
                    sound=True
                )
                return

            # Enable file watching
            logging.info("Enabling file watching")
            self.watch_toggle.state = True # Update the correct item's state
            self.watch_enabled = True

            fswatch_config = get_fswatch_config()
            logging.debug(f"Creating file watcher for {fswatch_config['local_dir']}")
            self.file_watcher = FileWatcher(
                fswatch_config['local_dir'],
                self.on_files_changed,
                fswatch_config['watch_delay']
            )

            if self.file_watcher.start():
                logging.info("File watcher started successfully")
                rumps.notification( # Reverted to rumps.notification
                    "TurboSync",
                    "File Watching Enabled",
                    f"Now watching {fswatch_config['local_dir']} for changes",
                    sound=False
                )
            else:
                logging.error("Failed to start file watcher")
                self.watch_toggle.state = False # Update the correct item's state
                self.watch_enabled = False

    @rumps.clicked("Sync Now") # Keep decorator
    def sync_now(self, _):
        logging.debug("Sync Now clicked")
        if self.syncing:
            logging.info("Sync already in progress, ignoring request")
            rumps.notification( # Reverted to rumps.notification
                "TurboSync",
                "Sync in Progress",
                "A sync operation is already running",
                sound=False
            )
            return

        logging.info("Starting sync thread")
        self.sync_thread = threading.Thread(target=self.perform_sync_task)
        self.sync_thread.start()

    def _check_sync_progress(self, timer):
        """Callback for the progress timer to check the queue."""
        if not self.syncing:
            logging.debug("Syncing stopped, stopping progress timer.")
            if self.progress_timer:
                self.progress_timer.stop()
                self.progress_timer = None
            return # Stop checking if sync is no longer active

        try:
            while not self.progress_queue.empty():
                message = self.progress_queue.get_nowait()
                if message and isinstance(message, dict):
                    msg_type = message.get('type')
                    project_name = message.get('project', 'Unknown Project')
                    if msg_type == 'start':
                        logging.info(f"Progress: Started syncing {project_name}")
                        # Update status immediately - safe within timer callback on main thread
                        self.status_item.title = f"Status: Syncing {project_name}..."
                    elif msg_type == 'progress':
                        percentage = message.get('percentage')
                        path = message.get('path')
                        if path is not None and percentage is not None:
                            logging.debug(f"Progress Update: {project_name} at {percentage}%")
                            self.active_sync_progress[path] = percentage
                            # Update the submenu to reflect the new percentage
                            self.update_synced_projects_list() # Update UI immediately
                    elif msg_type == 'end':
                        path = message.get('path')
                        success = message.get('success') # Get success status from message
                        success_status = "successfully" if success else "with errors"
                        logging.info(f"Progress: Finished syncing {project_name} {success_status}")
                        # Remove from active progress (end message means sync process for this dir finished)
                        if path in self.active_sync_progress:
                            del self.active_sync_progress[path]
                        # NOTE: The final result dict (with files/errors) is now aggregated in perform_sync
                        # and stored in self.last_sync_results after the sync thread finishes.
                        # We just need to trigger a UI update here to show the final state icon (✅/❌/etc.)
                        # We can temporarily store the simple success/fail here if needed for immediate UI update,
                        # but it will be overwritten by the full results later.
                        # Let's rely on update_synced_projects_list() being called after perform_sync finishes.
                        # Triggering an update here ensures the percentage disappears.
                        self.update_synced_projects_list()

        except multiprocessing.queues.Empty:
            pass # Queue is empty, nothing to do
        except Exception as e:
           logging.error(f"Error checking progress queue: {e}")

       # Update status panel if visible
       if self.status_panel_window and self.status_panel_window.isVisible():
            try:
                combined_status = self._get_combined_status()
                self.status_panel_window.update_status(combined_status)
            except Exception as panel_update_err:
                logging.error(f"Error updating status panel during progress check: {panel_update_err}")

   def perform_sync_task(self):
       """Run the sync in a separate thread and schedule UI updates."""
        logging.debug("Starting sync task")
        self.syncing = True

        # Start the progress checking timer (runs every 0.5 seconds)
        if self.progress_timer is None:
             logging.debug("Starting progress timer.")
             self.progress_timer = rumps.Timer(self._check_sync_progress, 0.5)
             self.progress_timer.start()
        else:
             logging.warning("Progress timer already exists, not starting again.")


        # Initial status update (safe from background thread before long operation)
        try:
            self.status_item.title = "Status: Starting sync..." # More generic start message
        except Exception as ui_err:
            # Log if the initial status update fails, but proceed with sync
            logging.error(f"Failed to set initial 'Starting sync...' status: {ui_err}")

        overall_success = False # Default overall status
        sync_results = None # Store detailed results here
        sync_message = "Sync did not run or failed unexpectedly." # Default message for overall status

        try:
            # --- Call the core sync logic, passing the queue ---
            logging.debug("Calling perform_sync() with progress queue...")
            sync_results = perform_sync(progress_queue=self.progress_queue) # Pass the queue
            logging.debug(f"perform_sync() returned: {sync_results}")

            # Determine overall success and message based on detailed results
            if isinstance(sync_results, dict):
                total_dirs = len(sync_results)
                successful_syncs = sum(1 for success in sync_results.values() if success)
                overall_success = total_dirs == 0 or successful_syncs == total_dirs # True if no dirs or all succeeded
                if total_dirs == 0:
                    sync_message = "No projects found to sync."
                elif overall_success:
                    sync_message = f"Synced {successful_syncs}/{total_dirs} projects successfully."
                else:
                    sync_message = f"Sync completed with {total_dirs - successful_syncs} failures out of {total_dirs} projects."
            else:
                # perform_sync returned None (config error or major exception)
                overall_success = False
                sync_message = "Sync failed due to configuration or system error."

            # --- Show Notification based on sync result (safe from background thread) ---
            # Notifications are generally thread-safe in rumps/macOS
            if overall_success:
                logging.info(f"Sync completed successfully: {sync_message}")
                try:
                    rumps.notification(
                        "TurboSync",
                        "Sync Completed",
                        sync_message,
                        sound=False
                    )
                except Exception as ne:
                    logging.error(f"Failed to show success notification: {ne}")
            else:
                logging.error(f"Sync failed: {sync_message}")
                try:
                    rumps.notification(
                        "TurboSync",
                        "Sync Failed",
                        sync_message,
                        sound=True
                    )
                except Exception as ne:
                    logging.error(f"Failed to show failure notification: {ne}")

        except Exception as e:
            # --- Handle exceptions during perform_sync() itself ---
            # This catch block might be less likely to be hit now that perform_sync handles its own exceptions,
            # but kept for safety.
            logging.exception(f"Unexpected exception during perform_sync call: {e}")
            overall_success = False # Ensure success is false on exception
            sync_message = f"An error occurred during sync: {str(e)}" # Use message from exception
            try:
                # Try to show an error notification for this specific exception
                rumps.notification(
                    "TurboSync",
                    "Sync Error",
                    sync_message,
                    sound=True
                )
            except Exception as ne:
                 logging.error(f"Failed to show error notification after exception: {ne}")

        finally:
            # --- Schedule Final UI Update on Main Thread ---
            # This block runs regardless of whether an exception occurred in the try block.
            # It ensures the status is always updated and syncing flag reset correctly.
            logging.debug(f"Scheduling final status update via timer with overall_success={overall_success}")
            try:
                # Use functools.partial to pass data to the callback
                update_callback = functools.partial(
                    self._update_status_after_sync,
                    overall_success,
                    sync_message,
                    sync_results
                )
                # Use a very short interval (e.g., 0.1s) just to defer execution to the main loop
                rumps.Timer(update_callback, 0.1).start()
                logging.debug("Timer scheduled for final status update.")
            except Exception as timer_e:
                # If scheduling the timer fails, log the error.
                # The syncing flag might remain True, which is problematic,
                # but trying to set it here is still unsafe.
                logging.error(f"CRITICAL: Failed to schedule status update timer: {timer_e}")
                # Consider adding more robust error handling here if needed,
                # e.g., trying to set a flag for the main thread to check later.

        logging.debug("Sync task thread finishing.")
        # DO NOT update self.status_item.title or self.syncing here.
        # It will be handled by _update_status_after_sync on the main thread.

    def _update_status_after_sync(self, overall_success, sync_message, sync_results, timer):
        """
        Update status item, syncing flag, and project list on the main thread after sync.
        Called via functools.partial, so arguments come first, then the timer object.
        """
        # Arguments overall_success, sync_message, sync_results are passed via partial
        # 'timer' is the rumps.Timer object passed automatically to the callback

        # Store the detailed results received from the sync task
        self.last_sync_results = sync_results

        try:
            logging.debug(f"Timer callback: Updating status after sync (overall_success={overall_success})")
            self.last_sync_status = f"Last sync: {time.strftime('%H:%M:%S')} - {'Success' if overall_success else 'Failed'}"
            logging.debug(f"Timer callback: New status string: {self.last_sync_status}")

            logging.debug("Timer callback: Updating status_item title...")
            self.status_item.title = f"Status: {self.last_sync_status}"
            logging.debug("Timer callback: Status_item title updated.")

            # Update the project list submenu with the new status details
            logging.debug("Timer callback: Updating synced projects list...")
            self.update_synced_projects_list()
            logging.debug("Timer callback: Synced projects list updated.")

            logging.debug("Timer callback: Setting self.syncing = False")
            self.syncing = False
            logging.debug("Timer callback: Status update complete.")

            # Stop the progress timer now that sync is finished
            if self.progress_timer:
                logging.debug("Stopping progress timer.")
               logging.debug("Stopping progress timer.")
               self.progress_timer.stop()
               self.progress_timer = None

           # Update status panel if visible
           if self.status_panel_window and self.status_panel_window.isVisible():
               try:
                   combined_status = self._get_combined_status()
                   self.status_panel_window.update_status(combined_status)
               except Exception as panel_update_err:
                   logging.error(f"Error updating status panel after sync: {panel_update_err}")

       except Exception as e:
           logging.exception(f"Exception during timer-based status update: {e}")
            # Attempt to set syncing to False and stop timer even if status update fails
            self.syncing = False
            if self.progress_timer:
                self.progress_timer.stop()
                self.progress_timer = None
            self.last_sync_results = None # Indicate error state
            self.update_synced_projects_list() # Update list to show error

    def scheduled_sync(self):
        """Run the scheduled sync if not already syncing"""
        logging.debug("Scheduled sync triggered")
        if not self.syncing:
            logging.info("Starting scheduled sync")
            self.sync_thread = threading.Thread(target=self.perform_sync_task)
            self.sync_thread.start()
        else:
            logging.debug("Skipping scheduled sync (sync already in progress)")

    @rumps.clicked("View Logs") # Keep decorator
    def view_logs(self, _):
        logging.debug("View Logs clicked")
        log_path = os.path.expanduser('~/Library/Logs/TurboSync/turbosync.log')
        if os.path.exists(log_path):
            logging.info(f"Opening log file at: {log_path}")
            os.system(f"open {log_path}")
        else:
            logging.warning(f"Log file not found at: {log_path}")
            rumps.notification( # Reverted to rumps.notification
                "TurboSync",
                "Logs Not Found",
                "No log file exists yet.",
                sound=False
            )

    def update_synced_projects_list(self):
        """
        Updates the submenu showing the list of synced projects.
        Uses self.last_sync_results to add status indicators (e.g., for errors).
        Assumes self.last_sync_results is populated before this is called after a sync.
        """
        logging.debug("Updating synced projects list menu item")

        # Clear existing items in the submenu first
        self.synced_projects_item.clear()

        if not hasattr(self, 'config') or not self.config:
            logging.warning("Cannot update synced projects list: config not loaded.")
            self.synced_projects_item.title = "Synced Projects" # Keep title simple
            self.synced_projects_item.add(rumps.MenuItem("Config Error"))
            return

        try:
            livework_dirs = sorted(find_livework_dirs(self.config)) # Sort for consistent order
            count = len(livework_dirs)
            logging.info(f"Found {count} synced projects.")
            self.synced_projects_item.title = f"Synced Projects ({count})" # Update title with count
            if count > 0:
                for dir_path in livework_dirs:
                    base_name = os.path.basename(dir_path)
                    item_title = base_name # Start with base name

                    # 1. Check if currently syncing (highest priority)
                    if dir_path in self.active_sync_progress:
                        percentage = self.active_sync_progress[dir_path]
                        item_title = f"{base_name} ({percentage}%)"
                        project_item = rumps.MenuItem(item_title) # Create item with progress

                    # 2. Else, check last sync result details for this specific path
                    elif isinstance(self.last_sync_results, dict) and dir_path in self.last_sync_results:
                        result_data = self.last_sync_results[dir_path]
                        project_item = rumps.MenuItem(base_name) # Create item first

                        if isinstance(result_data, dict): # Should always be a dict now
                            if result_data.get('success') is True:
                                item_title = f"✅ {base_name}"
                                project_item.title = item_title
                                # Add "View Synced Files" submenu if files exist
                                synced_files = result_data.get('synced_files', [])
                                if synced_files:
                                     files_item = rumps.MenuItem(f"View {len(synced_files)} Synced File(s)")
                                     # Pass the list of files to the callback
                                     files_item.set_callback(functools.partial(self._show_synced_files, project_name=base_name, files=synced_files))
                                     project_item.add(files_item)
                                else:
                                     project_item.add(rumps.MenuItem("No files transferred"))

                            elif result_data.get('success') is False:
                                error_msg = result_data.get('error', 'Unknown error')
                                # Check for specific error types if implemented (e.g., lock file)
                                if result_data.get('error_type') == 'lock_file': # Example check
                                     item_title = f"⚠️ {base_name}" # Lock indicator
                                     project_item.title = item_title
                                     lock_file_path = result_data.get('path') # Assuming path is stored for lock errors
                                     if lock_file_path:
                                         action_item = rumps.MenuItem("Remove Lock File & Retry Sync")
                                         action_item.set_callback(functools.partial(self._remove_lock_file_and_retry, lock_file_path=lock_file_path))
                                         project_item.add(action_item)
                                     # Also add view error for lock files
                                     error_item = rumps.MenuItem("View Error")
                                     error_item.set_callback(functools.partial(self._show_error_message, project_name=base_name, error=error_msg))
                                     project_item.add(error_item)
                                else: # General failure
                                     item_title = f"❌ {base_name}" # Failure indicator
                                     project_item.title = item_title
                                     # Add "View Error" submenu
                                     error_item = rumps.MenuItem("View Error")
                                     # Pass the error message to the callback
                                     error_item.set_callback(functools.partial(self._show_error_message, project_name=base_name, error=error_msg))
                                     project_item.add(error_item)
                        else:
                             # Should not happen if sync.py returns dicts, but handle defensively
                             item_title = f"❓ {base_name}" # Unknown status indicator
                             project_item.title = item_title

                    # 3. Else, check for general sync error state (last_sync_results is None but dirs exist)
                    elif self.last_sync_results is None and count > 0:
                        item_title = f"❓ {base_name}" # Prepend general error indicator
                        project_item = rumps.MenuItem(item_title)

                    # 4. Default: Just show the name (e.g., first run, or sync hasn't touched this dir)
                    else:
                        project_item = rumps.MenuItem(item_title) # Item with just the base name

                    self.synced_projects_item.add(project_item) # Add the constructed item
            else:
                self.synced_projects_item.add(rumps.MenuItem("No projects found"))
        except Exception as e:
            logging.error(f"Error finding livework directories: {e}")
            self.synced_projects_item.title = "Synced Projects" # Keep title simple
            self.synced_projects_item.add(rumps.MenuItem("Error loading projects"))

    # --- Helper Functions for Login Item ---

    def _remove_lock_file_and_retry(self, lock_file_path, sender=None):
        """Callback to remove a specific rclone lock file and trigger sync."""
        if not lock_file_path:
            logging.error("Remove lock file called without a path.")
            rumps.notification("TurboSync Error", "Cannot remove lock file", "No path provided.")
            return

        logging.info(f"Attempting to remove lock file: {lock_file_path}")

        # Find rclone executable
        rclone_executable = os.environ.get('RCLONE_PATH', shutil.which('rclone'))
        if not rclone_executable:
             logging.error("rclone executable not found for lock file removal.")
             rumps.notification("TurboSync Error", "rclone Not Found", "Cannot find rclone to remove lock file.")
             return

        try:
            cmd = [rclone_executable, "deletefile", lock_file_path]
            logging.debug(f"Executing command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logging.info(f"Successfully removed lock file: {lock_file_path}")
            logging.debug(f"rclone deletefile output: {result.stdout} {result.stderr}")
            rumps.notification("TurboSync", "Lock File Removed", "Attempting sync again...")
            # Trigger a new sync
            self.sync_now(None)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to remove lock file '{lock_file_path}': {e.stderr}")
            rumps.notification("TurboSync Error", "Failed to Remove Lock File", f"Error: {e.stderr[:100]}")
        except Exception as e:
            logging.exception(f"Unexpected error removing lock file '{lock_file_path}': {e}")
            rumps.notification("TurboSync Error", "Failed to Remove Lock File", f"Unexpected error: {e}")

    # --- Callbacks for Details Submenu ---
    def _show_synced_files(self, project_name, files, sender=None):
        """Displays the list of synced files in a rumps alert."""
        logging.info(f"Showing synced files for project: {project_name}")
        if not files:
            message = "No files were reported as transferred in the last sync."
        else:
            # Join files with newline, limit total length for alert box
            message = "Files transferred:\n\n" + "\n".join(files)
            if len(message) > 800: # Limit message size for alert
                 message = message[:797] + "...\n\n(List truncated)"

        # Use rumps.alert for a simple modal display
        try:
             # Ensure this runs on the main thread if called from background
             # (though callbacks usually run on main thread in rumps)
             rumps.alert(title=f"Synced Files: {project_name}", message=message, ok="OK")
        except Exception as e:
             logging.error(f"Failed to show synced files alert: {e}")
             # Fallback notification
             rumps.notification("TurboSync", f"Synced Files: {project_name}", f"{len(files)} files transferred.")

    def _show_error_message(self, project_name, error, sender=None):
        """Displays the sync error message in a rumps alert."""
        logging.info(f"Showing error for project: {project_name}")
        # Format the error message nicely
        message = f"An error occurred while syncing '{project_name}':\n\n"
        # Wrap long lines for better readability in the alert box
        wrapped_error = textwrap.fill(str(error), width=70) # Ensure error is string, adjust width as needed
        message += wrapped_error
        if len(message) > 800: # Limit message size
             message = message[:797] + "...\n\n(Error message truncated)"

        try:
             # Ensure this runs on the main thread
             rumps.alert(title=f"Sync Error: {project_name}", message=message, ok="OK")
        except Exception as e:
             logging.error(f"Failed to show error alert: {e}")
             # Fallback notification
             rumps.notification("TurboSync Error", f"Error syncing {project_name}", str(error)[:100]) # Show truncated error
    # --- End Callbacks ---

    def _get_app_path(self):
        """Determines the path to the running application bundle (.app)."""
        logging.debug("Determining application path...")
        # When running as a bundled app, sys.executable is inside the bundle
        # e.g., /Applications/TurboSync.app/Contents/MacOS/python
        if ".app/Contents/MacOS/" in sys.executable:
            # Go up three levels to get the .app path
            app_path = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '..', '..', '..'))
            logging.debug(f"Detected running as bundled app. Path: {app_path}")
            return app_path
        else:
            # Likely running from source (e.g., python main.py)
            # In this case, adding to login items might not be the desired behavior,
            # or we might need a different approach (e.g., launching the source script).
            # For now, return None to indicate it's not a standard .app launch.
            logging.warning("Not running as a bundled .app. Cannot determine .app path for login item.")
            return None

    def _set_login_item(self, enable):
        """Adds or removes the application from macOS Login Items using AppleScript."""
        app_path = self._get_app_path()
        if not app_path:
            logging.error("Cannot set login item: Application path not found (not running as .app?).")
            rumps.notification("TurboSync Error", "Login Item Failed", "Could not determine application path.")
            return False

        app_name = os.path.basename(app_path).replace('.app', '')
        logging.info(f"{'Enabling' if enable else 'Disabling'} login item for {app_name} at {app_path}")

        try:
            if enable:
                script = f'''
                tell application "System Events"
                    if not (exists login item "{app_name}") then
                        make new login item at end with properties {{path:"{app_path}", hidden:false}}
                        log "Added login item: {app_name}"
                    else
                        log "Login item already exists: {app_name}"
                    end if
                end tell
                '''
            else:
                script = f'''
                tell application "System Events"
                    if (exists login item "{app_name}") then
                        delete login item "{app_name}"
                        log "Deleted login item: {app_name}"
                    else
                        log "Login item does not exist: {app_name}"
                    end if
                end tell
                '''
            
            # Execute the AppleScript
            process = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, check=True)
            logging.info(f"AppleScript execution successful for login item: {process.stdout.strip()}")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"AppleScript execution failed for login item: {e}")
            logging.error(f"AppleScript stderr: {e.stderr}")
            rumps.notification("TurboSync Error", "Login Item Failed", f"Could not {'add' if enable else 'remove'} login item: {e.stderr[:100]}")
            return False
        except Exception as e:
            logging.exception(f"Unexpected error setting login item: {e}")
            rumps.notification("TurboSync Error", "Login Item Failed", f"Unexpected error: {e}")
            return False

    # --- End Helper Functions ---

    def _load_current_settings(self):
        """Loads current settings from the user's .env file."""
        logging.debug(f"Attempting to load settings from {USER_ENV_PATH}")
        if not os.path.exists(USER_ENV_PATH):
            logging.warning(f"User settings file not found at {USER_ENV_PATH} when trying to load for dialog.")
            # Attempt to ensure it exists by calling the function from main.py
            # This requires importing ensure_env_file
            try:
                from turbo_sync.main import ensure_env_file
                logging.debug("Calling ensure_env_file to potentially create settings file.")
                ensure_env_file() # Try to create it if missing
                if not os.path.exists(USER_ENV_PATH):
                     logging.error("ensure_env_file was called, but settings file still not found.")
                     return {} # Return empty if still not found
            except ImportError:
                 logging.error("Could not import ensure_env_file from main.py")
                 return {} # Cannot ensure file exists
            except Exception as e:
                 logging.error(f"Error calling ensure_env_file: {e}")
                 return {}
            # For simplicity here, we'll just return defaults if it's missing
            # A more robust solution might call ensure_env_file from main.py
            return {}
        try:
            return dotenv_values(USER_ENV_PATH)
        except Exception as e:
            logging.error(f"Error reading settings file {USER_ENV_PATH}: {e}")
            return {}

    def _save_settings(self, new_settings):
        """Saves the settings back to the user's .env file."""
        logging.info(f"Saving settings to {USER_ENV_PATH}")
        try:
            # Ensure the directory exists
            os.makedirs(USER_CONFIG_DIR, exist_ok=True)
            # Use set_key to update or add values in the .env file
            # This preserves comments and structure better than rewriting
            for key, value in new_settings.items():
                 # Ensure value is a string for set_key
                 str_value = str(value) if value is not None else ''
                 set_key(USER_ENV_PATH, key, str_value, quote_mode="never")
            logging.info("Settings saved successfully.")

            # Reload config in the running app
            logging.info(f"Reloading configuration after save using path: {USER_ENV_PATH}")
            self.config = load_config(dotenv_path=USER_ENV_PATH) # Pass the path
            if not self.config: # load_config might return None or raise error handled below
                 raise ValueError("load_config failed to return a valid configuration after save.")
            logging.info(f"New sync interval: {self.config['sync_interval']} minutes")

            # Reschedule the sync job
            schedule.clear()
            schedule.every(self.config['sync_interval']).minutes.do(self.scheduled_sync)
            logging.info("Rescheduled sync job.")

            # Restart file watcher if settings changed
            # Compare new watch setting with current state
            new_watch_enabled = str(new_settings.get('WATCH_LOCAL_FILES', 'false')).lower() == 'true'
            if new_watch_enabled != self.watch_enabled:
                 logging.info(f"Watch setting changed to {new_watch_enabled}. Toggling watcher.")
                 # Use the existing toggle logic but force the state
                 self.watch_toggle.state = not new_watch_enabled # Set to opposite so toggle works
                 self.toggle_file_watching(self.watch_toggle)
            elif self.watch_enabled:
                 # If watch enabled and path/delay changed, restart watcher
                 fswatch_config = get_fswatch_config()
                 new_local_dir = new_settings.get('LOCAL_DIR', '')
                 new_delay = int(new_settings.get('WATCH_DELAY_SECONDS', 2))
                 if (fswatch_config['local_dir'] != new_local_dir or
                     fswatch_config['watch_delay'] != new_delay):
                     logging.info("Watcher config changed. Restarting watcher.")
                     if self.file_watcher:
                         self.file_watcher.stop()
                     self.setup_file_watcher() # Re-setup with new config
 
            # --- Handle Start at Login ---
            start_at_login = str(new_settings.get('START_AT_LOGIN', 'false')).lower() == 'true'
            self._set_login_item(start_at_login)
            # --- End Handle Start at Login ---
 
            return True
        except Exception as e:
            logging.exception(f"Error saving settings to {USER_ENV_PATH}: {e}")
            rumps.notification("TurboSync Error", "Save Failed", f"Could not save settings: {e}") # Reverted to rumps.notification
            return False

# --- Removed old @rumps.clicked("Settings") and show_settings_dialog method ---


# --- Update TurboSyncMenuBar ---

    @rumps.clicked("Settings") # Restore decorator
    def launch_pyside_settings(self, sender): # Keep sender argument for manual callbacks
        """Loads settings and calls the external function from settings_dialog.py to display the PySide6 dialog."""
        # Log which item triggered it if needed (sender is the MenuItem)
        logging.info(f"Settings menu item clicked (triggered manually via {sender.title if sender else 'Unknown'}).")
        try:
            logging.debug("Attempting to load current settings for dialog.")
            current_settings = self._load_current_settings()
            logging.debug(f"Loaded settings: {current_settings}")

            # Call the imported function, passing self (the menubar app instance) and the settings
            launch_pyside_settings_dialog(self, current_settings)

        except Exception as e:
            # Catch errors during setting loading or the call itself
            logging.exception("An error occurred preparing or launching the settings dialog")
            rumps.notification("TurboSync Error", "Settings Error", f"Could not prepare settings: {e}")


    # Removed custom quit_app method and decorator. Relying entirely on default rumps Quit button.
    # The default Quit button should call rumps.quit_application()


def run_app():
    logging.info("Starting TurboSync app")
    try:
        # Ensure we're running in the main thread
        if threading.current_thread() is not threading.main_thread():
            logging.error("TurboSync must be run from the main thread")
            return

        # Create and run the app
        app = TurboSyncMenuBar()

        # Start the scheduler in a background thread
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        logging.info("Scheduler thread started")

        # Run the app - this call blocks until the app quits
        logging.info("Starting rumps application")
        try:
            app.run()
            logging.info("rumps application has exited")
        except Exception as e:
            logging.exception(f"Error running rumps application: {e}")
            # Try to show an error notification
            try:
                rumps.notification( # Reverted to rumps.notification
                    "TurboSync Error",
                    "Application Error",
                    f"Failed to start menubar app: {str(e)}",
                    sound=True
                )
            except:
                pass
            raise
    except Exception as e:
        logging.exception(f"Error starting app: {e}")
        raise

def run_scheduler():
    """Run the scheduler in a separate thread"""
    logging.info("Scheduler thread started")
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logging.exception(f"Error in scheduler thread: {e}")
            time.sleep(5)  # Pause a bit longer if there's an error
