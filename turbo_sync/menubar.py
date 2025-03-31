import os
import sys
import time
import threading
import logging
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

from turbo_sync.sync import perform_sync, load_config # Absolute import
from turbo_sync.watcher import FileWatcher, is_fswatch_available, get_fswatch_config # Absolute import
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

        # --- Define Items Needing State Management First ---
        self.status_item = rumps.MenuItem(f"Status: {self.last_sync_status}")
        self.watch_toggle = rumps.MenuItem("Enable File Watching") # Title matches decorator

        # --- Define Complete Menu Structure ---
        # Construct the list with MenuItem objects included directly
        menu_items = [
            self.status_item,       # Insert the MenuItem object
            "Sync Now",
            "View Logs",
            None,                   # Separator
            self.watch_toggle,      # Insert the MenuItem object
            "Settings",
            None,                   # Separator
            # Quit item added by rumps automatically
        ]
        self.menu = menu_items      # Assign the final list to self.menu

        # Load configuration
        try:
            logging.debug("Loading configuration")
            self.config = load_config()
            logging.info(f"Configuration loaded, sync interval: {self.config['sync_interval']} minutes")
            schedule.every(self.config['sync_interval']).minutes.do(self.scheduled_sync)

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

    def perform_sync_task(self):
        """Run the sync in a separate thread"""
        logging.debug("Starting sync task")
        self.syncing = True
        self.status_item.title = "Status: Syncing..."
        success = False # Default to False
        sync_message = "Sync did not run or failed unexpectedly." # Default message

        try:
            # --- Call perform_sync ---
            logging.debug("Calling perform_sync()...")
            success, sync_message = perform_sync() # Get result from perform_sync
            logging.debug(f"perform_sync() returned: success={success}, message='{sync_message}'")

            # --- Show Notification based on sync result ---
            if success:
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
            # --- Handle exceptions during perform_sync() or initial notifications ---
            logging.exception(f"Exception during sync task (perform_sync call or notification): {e}")
            success = False # Ensure success is false on exception
            sync_message = f"An error occurred during sync: {str(e)}" # Use message from exception
            try:
                # Try to show an error notification for this exception
                rumps.notification(
                    "TurboSync",
                    "Sync Error",
                    sync_message,
                    sound=True
                )
            except Exception as ne:
                 logging.error(f"Failed to show error notification after exception: {ne}")

        # --- Code after perform_sync() call (runs regardless of success/failure/exception) ---
        try:
            logging.debug("Updating last sync status string...")
            self.last_sync_status = f"Last sync: {time.strftime('%H:%M:%S')} - {'Success' if success else 'Failed'}"
            logging.debug(f"New status string: {self.last_sync_status}")

            logging.debug("Updating status_item title...")
            self.status_item.title = f"Status: {self.last_sync_status}" # Rumps call
            logging.debug("<<< Status_item title update attempted >>>") # ADDED THIS LINE
            logging.debug("Status_item title updated.") # Original line moved down

            logging.debug("Setting self.syncing = False")
            self.syncing = False
            logging.debug("Sync task thread finishing cleanly.") # Added final log

        except Exception as e_after:
             # --- Handle exceptions during the status update phase ---
             logging.exception(f"Exception *after* sync completed/failed, during status update: {e_after}")
             # Try to show a notification about this specific error
             try:
                 rumps.notification(
                     "TurboSync",
                     "Internal Error",
                     f"Error updating status after sync: {str(e_after)}",
                     sound=True
                 )
             except Exception as ne2:
                 logging.error(f"Failed to show post-sync error notification: {ne2}")
             # Ensure syncing flag is reset even if status update fails
             logging.debug("Setting self.syncing = False after exception during status update.")
             self.syncing = False

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

    # --- Helper Functions for Login Item ---

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
            logging.info("Reloading configuration after save.")
            self.config = load_config()
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
