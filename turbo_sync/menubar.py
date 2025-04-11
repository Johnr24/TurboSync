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
# import multiprocessing # Import multiprocessing for Queue and Manager # Removed
import textwrap # For formatting long messages
from turbo_sync.utils import get_resource_path # Import from utils
# --- Import the Settings Dialog logic ---
from turbo_sync.settings_dialog import launch_pyside_settings_dialog # Import the launcher function
# --- Imports needed for Status Panel ---
from PySide6.QtWidgets import QApplication # Keep QApplication
from PySide6.QtCore import QObject, Signal # Add QObject, Signal
from turbo_sync.status_panel import StatusPanel

# Define user-specific config path (consistent with main.py)
APP_NAME = "TurboSync"
USER_CONFIG_DIR = os.path.expanduser(f'~/Library/Application Support/{APP_NAME}')
USER_ENV_PATH = os.path.join(USER_CONFIG_DIR, '.env')

# Add this class definition ABOVE the TurboSyncMenuBar class definition
class SyncSignalEmitter(QObject):
    """Helper class to emit signals for sync progress."""
    sync_progress_update = Signal(dict) # Signal payload is a dictionary

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
        self.is_syncing = False # Use this instead of self.syncing
        self.sync_thread = None
        # self.status_item = None # Defined below
        self.last_sync_status = "Never synced"
        self.file_watcher = None
        self.watch_enabled = False # Will be updated by setup_file_watcher
        self.last_sync_results = {} # Store detailed results {path: {'success': bool, 'synced_files': [], 'error': 'msg', 'error_type': 'optional_str'}}
        # self.active_sync_progress = {} # Store current progress {path: percentage} # Removed
        # Use Manager().Queue() for inter-process communication with ProcessPoolExecutor # Removed
        # self.manager = multiprocessing.Manager() # Removed
        # self.progress_queue = self.manager.Queue() # Queue for sync progress # Removed
        # self.progress_timer = None # Timer to check the queue # Removed
        self.status_panel = None # Changed from self.status_panel_window
        self.sync_emitter = SyncSignalEmitter() # Add emitter

        # --- Define Items Needing State Management First ---
        self.status_item = rumps.MenuItem(f"Status: {self.last_sync_status}")
        self.watch_toggle = rumps.MenuItem("Enable File Watching") # Title matches decorator
        # Synced projects submenu removed

        # --- Define Complete Menu Structure ---
        self.status_panel_item = rumps.MenuItem("Show Sync Status") # New item
        self.status_panel_item.set_callback(self.show_status_panel) # Explicitly set callback
        # Construct the list with MenuItem objects included directly
        menu_items = [
            self.status_item,       # Insert the MenuItem object
            "Sync Now",
            self.status_panel_item, # Add the new item here
           "View Logs",
           # Synced projects submenu removed
           None,                   # Separator
           self.watch_toggle,      # Insert the MenuItem object
            "Settings",
            None,                   # Separator
            # Quit item added by rumps automatically
            rumps.MenuItem("Open Sync Dashboard", callback=self.show_status_panel) # Added here
        ]
        self.menu = menu_items      # Assign the final list to self.menu
        # Removed self.menu.append(...) line

        # Synced projects submenu removed

        # Load configuration
        try:
            logging.debug(f"Loading configuration using path: {USER_ENV_PATH}")
            self.config = load_config(dotenv_path=USER_ENV_PATH) # Pass the path
            if not self.config: # load_config might return None or raise error handled below
                raise ValueError("load_config failed to return a valid configuration.")
            logging.info(f"Configuration loaded, sync interval: {self.config['sync_interval']} minutes")
            schedule.every(self.config['sync_interval']).minutes.do(self.scheduled_sync)

            # Synced projects submenu removed

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
        if not self.is_syncing: # Use correct flag
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

        self.perform_sync_task() # Call the task handler

    # --- New perform_sync_task method (replaces old one and _check_sync_progress/_update_status_after_sync) ---
    def perform_sync_task(self):
        """Handles the execution of the sync process in a separate thread."""
        if self.is_syncing:
            logging.warning("Sync task requested, but sync is already in progress.")
            rumps.notification("Sync In Progress", "", "A synchronization task is already running.")
            # Ensure panel is visible if sync is ongoing and panel exists
            if self.status_panel and not self.status_panel.isVisible():
                self.show_status_panel()
            return

        logger.info("Starting sync task...")
        self.is_syncing = True
        # Update UI to indicate syncing (e.g., disable button, change icon/status)
        self.status_item.title = "Status: Syncing..."
        # Consider disabling the "Sync Now" menu item temporarily if needed
        # self.menu["Sync Now"].set_callback(None) # Example: Disable callback

        # Show the status panel (this also clears it)
        self.show_status_panel()

        # Define the target function for the background thread
        def sync_thread_target():
            logger.info("Sync thread started.")
            final_results = None
            overall_success = False
            sync_message = "Sync finished."
            try:
                # Pass the signal emitter to perform_sync
                # NOTE: Assumes perform_sync is updated to accept 'signal_emitter'
                final_results = perform_sync(signal_emitter=self.sync_emitter)

                # --- Sync Finished ---
                if final_results is not None: # Check if sync ran (wasn't a config error)
                    successful_syncs = sum(1 for res in final_results.values() if res.get('success', False))
                    total_dirs = len(final_results)
                    overall_success = total_dirs == 0 or successful_syncs == total_dirs
                    if total_dirs == 0:
                        sync_message = "No projects found to sync."
                    elif overall_success:
                        sync_message = f"Synced {successful_syncs}/{total_dirs} projects successfully."
                    else:
                        sync_message = f"Sync completed with {total_dirs - successful_syncs} failures out of {total_dirs} projects."

                    logger.info(f"Sync task completed in thread. {sync_message}")
                    # Show notification (safe from thread)
                    rumps.notification(
                        "TurboSync",
                        "Sync Complete" if overall_success else "Sync Finished with Errors",
                        sync_message,
                        sound=not overall_success # Sound on failure
                    )
                    # Optionally emit one final signal for overall completion if needed by panel
                    # self.sync_emitter.sync_progress_update.emit({
                    #     'type': 'overall_end', 'success': overall_success,
                    #     'message': sync_message
                    # })
                else:
                    # perform_sync returned None (config error or major exception)
                    logger.error("Sync task failed with configuration or unexpected error.")
                    overall_success = False
                    sync_message = "Sync failed due to error. Check logs."
                    rumps.notification("TurboSync Sync Failed", sync_message, "", sound=True)
                    # Optionally emit final failure signal
                    # self.sync_emitter.sync_progress_update.emit({
                    #     'type': 'overall_end', 'success': False, 'message': sync_message
                    # })

            except Exception as e:
                logger.error(f"Exception in sync thread target: {e}")
                logger.exception("Traceback:")
                overall_success = False
                sync_message = f"Error during sync: {e}"
                rumps.notification("TurboSync Sync Error", sync_message, "", sound=True)
                # Optionally emit final failure signal
                # self.sync_emitter.sync_progress_update.emit({
                #     'type': 'overall_end', 'success': False, 'message': sync_message
                # })
            finally:
                # This block runs regardless of success or failure in the thread
                # Schedule the final UI update on the main thread using a timer
                update_callback = functools.partial(
                    self._finalize_sync_ui,
                    overall_success,
                    sync_message,
                    final_results # Pass results for potential future use
                )
                rumps.Timer(update_callback, 0.1).start()
                logger.debug("Scheduled final UI update from sync thread.")

        # Create and start the thread
        self.sync_thread = threading.Thread(target=sync_thread_target, daemon=True)
        self.sync_thread.start()

    # --- New method to finalize UI updates on main thread ---
    def _finalize_sync_ui(self, overall_success, sync_message, final_results, timer):
        """Updates the UI on the main thread after sync completion."""
        # 'timer' object is passed automatically by rumps.Timer
        logger.info("Finalizing sync UI on main thread.")
        self.is_syncing = False
        self.last_sync_status = f"Last sync: {time.strftime('%H:%M:%S')} - {'Success' if overall_success else 'Failed'}"
        self.status_item.title = f"Status: {self.last_sync_status}"
        self.last_sync_results = final_results # Store results if needed

        # Re-enable the "Sync Now" menu item if it was disabled
        # if self.menu["Sync Now"].callback is None:
        #    self.menu["Sync Now"].set_callback(self.sync_now)

        # Optional: Update status panel one last time if it's still open
        # if self.status_panel and self.status_panel.isVisible():
        #    # Maybe add a final summary message to the panel?
        #    pass

        logger.info("Sync UI finalized.")

    # --- Update scheduled_sync ---
    def scheduled_sync(self):
        """Run the scheduled sync if not already syncing"""
        logging.debug("Scheduled sync triggered")
        if not self.is_syncing: # Use the correct flag
            logging.info("Starting scheduled sync")
            # No need to create thread here, call the task handler
            self.perform_sync_task()
        else:
            logging.debug("Skipping scheduled sync (sync already in progress)")

    @rumps.clicked("View Logs") # Keep decorator
    def view_logs(self, _):
        """Opens the application's log file."""
        logging.debug("View Logs clicked")
        log_path = os.path.expanduser('~/Library/Logs/TurboSync/turbosync.log')
        if os.path.exists(log_path):
            logging.info(f"Opening log file at: {log_path}")
            # Use subprocess.run for better control and security than os.system
            try:
                subprocess.run(['open', log_path], check=True)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to open log file with 'open': {e}")
                rumps.notification("TurboSync Error", "Log Open Failed", f"Could not open log file: {e}")
            except FileNotFoundError:
                 logging.error("The 'open' command was not found.")
                 rumps.notification("TurboSync Error", "Log Open Failed", "The 'open' command is not available.")
        else:
            logging.warning(f"Log file not found at: {log_path}")
            rumps.notification( # Reverted to rumps.notification
                "TurboSync",
                "Logs Not Found",
                "No log file exists yet.",
                sound=False
            )

    # --- Synced Projects Submenu Removed ---

    # --- Helper Functions for Login Item ---

    # Note: The _get_app_path function definition starts below correctly.

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

    # --- Status Panel Methods ---

    # --- Remove old _get_combined_status method ---
    # def _get_combined_status(self): ... (entire method removed)


    # Replace the existing show_status_panel method
    def show_status_panel(self, sender=None): # Allow calling without sender
        """Creates (if needed), connects, clears, and shows the StatusPanel."""
        # Ensure QApplication instance exists for PySide dialogs
        app = QApplication.instance()
        if not app:
            logging.info("Creating QApplication instance for Status Panel.")
            # Use sys.argv if available, otherwise empty list
            app_args = sys.argv if hasattr(sys, 'argv') else []
            # Ensure it doesn't conflict if rumps already created one?
            # This might need careful handling depending on rumps/PySide interaction.
            # For now, assume creating it if needed is okay.
            app = QApplication(app_args)

        if self.status_panel is None:
            logger.info("Creating Status Panel instance.")
            try:
                self.status_panel = StatusPanel()
                # Connect the signal from the emitter to the panel's slot
                self.sync_emitter.sync_progress_update.connect(self.status_panel.update_status)
                # Connect the panel's closed signal to reset our reference
                self.status_panel.closed.connect(self._status_panel_closed)
                logger.info("Status Panel created and signals connected.")
            except Exception as e:
                logger.exception("Failed to create StatusPanel instance.")
                rumps.notification("TurboSync Error", "Status Panel Error", f"Could not create panel: {e}")
                return # Don't proceed if creation failed
        else:
            logger.info("Status Panel instance already exists.")

        # Clear previous results before showing
        try:
            self.status_panel.clear_status()
        except Exception as e:
             logger.error(f"Error calling clear_status on panel: {e}")

        # Show and raise the window
        try:
            self.status_panel.show()
            self.status_panel.raise_() # Bring to front
            self.status_panel.activateWindow() # Ensure focus
        except Exception as e:
             logger.error(f"Error showing/activating status panel: {e}")
             rumps.notification("TurboSync Error", "Status Panel Error", f"Could not show panel: {e}")

    # Add or ensure this method exists to handle the panel closing
    def _status_panel_closed(self):
        """Slot called when the status panel emits the 'closed' signal (is hidden)."""
        logging.debug("Status panel reported closed (hidden). Resetting reference.")
        # Set reference to None so it gets recreated next time if needed.
        # Or keep the reference if you want to reuse the same hidden window.
        # For simplicity, let's recreate it.
        self.status_panel = None

    # --- End Status Panel Methods ---

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
