import os
import sys
import functools # Import functools for partial
import time
import threading
import logging
import shutil # Import shutil
import rumps
import subprocess # Added for AppleScript execution
import multiprocessing # Import multiprocessing for Queue and Manager
# Removed explicit component imports for rumps 0.4.0
# from rumps import separator, Text, EditText, Checkbox, Window, MenuItem, App, notification, quit_application
import schedule
from dotenv import load_dotenv, set_key, dotenv_values # Added set_key, dotenv_values
from collections import OrderedDict # To maintain setting order

# --- PySide6 Imports (Removed - Now handled in settings_dialog.py) ---
# from PySide6.QtWidgets import QApplication, QDialog, ...
# from PySide6.QtCore import Qt, Slot

# Renamed perform_sync to update_syncthing_configuration
# Import necessary functions and constants
from turbo_sync.sync import update_syncthing_configuration, load_config, find_livework_dirs, DEFAULT_CONFIG
from turbo_sync.watcher import FileWatcher, is_fswatch_available, get_fswatch_config # Absolute import
import textwrap # For formatting long messages
import atexit # Import atexit for cleanup

from turbo_sync.utils import get_resource_path # Import from utils
# --- Import the Settings Dialog logic ---
from turbo_sync.settings_dialog import launch_pyside_settings_dialog # Import the launcher function
# --- Imports needed for Status Panel ---
from PySide6.QtWidgets import QApplication # Keep QApplication
from PySide6.QtCore import QObject, Signal # Add QObject, Signal
# --- Import Syncthing Manager ---
from turbo_sync.syncthing_manager import (
    start_syncthing_daemon, stop_syncthing_daemon, is_syncthing_running,
    SyncthingApiClient, get_api_key_from_config, generate_syncthing_config, # <-- Add here
    SYNCTHING_CONFIG_DIR_SOURCE, SYNCTHING_CONFIG_DIR_DEST, # Use specific dirs
    SYNCTHING_LOG_FILE_SOURCE, SYNCTHING_LOG_FILE_DEST, # Use specific logs
    USER_LOG_DIR) # Added imports # Corrected imports
from turbo_sync.status_panel import StatusPanel

# Set up module-level logger
logger = logging.getLogger(__name__)

# Define user-specific config path (consistent with main.py)
APP_NAME = "TurboSync"
USER_CONFIG_DIR = os.path.expanduser(f'~/Library/Application Support/{APP_NAME}')
USER_ENV_PATH = os.path.join(USER_CONFIG_DIR, '.env')

# --- Removed SyncSignalEmitter ---
# class SyncSignalEmitter(QObject):
#     """Helper class to emit signals for sync progress."""
#     sync_progress_update = Signal(dict) # Signal payload is a dictionary

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
        # self.is_syncing = False # Removed - Syncthing runs continuously
        self.config_update_thread = None # Thread for running config updates
        self.is_updating_config = False # Flag to prevent concurrent updates
        # self.status_item = None # Defined below
        self.last_config_update_status = "Never updated"
        self.file_watcher = None
        self.watch_enabled = False # Will be updated by setup_file_watcher
        # State for TWO Syncthing instances
        self.syncthing_process_source = None
        self.syncthing_process_dest = None
        self.api_client_source = None
        self.api_client_dest = None
        # --- End two instance state ---
        self.status_panel = None # Changed from self.status_panel_window
        self.status_poll_timer = None # Timer for polling Syncthing status (will poll both)
        self.scheduler_thread = None # Thread for scheduler

        # --- Define Items Needing State Management First ---
        self.status_item = rumps.MenuItem("Status: Initializing...")
        self.watch_toggle = rumps.MenuItem("Enable File Watching", callback=self.toggle_file_watching) # Add callback here
        self.update_config_item = rumps.MenuItem("Update Syncthing Config", callback=self.update_syncthing_config_task)
        self.status_dashboard_item = rumps.MenuItem("Open Sync Status Dashboard", callback=self.show_status_panel)

        # --- Define Complete Menu Structure ---
        menu_items = [
            self.status_item,
            self.update_config_item,
            self.status_dashboard_item,
            "View Logs",
            None,                   # Separator
            self.watch_toggle,
            "Settings",             # Keep Settings always enabled
            None,                   # Separator
            rumps.MenuItem("Quit TurboSync", callback=self.quit_app),
        ]
        self.menu = menu_items

        # --- Load Configuration and Initialize ---
        self._load_and_initialize()

    def _load_and_initialize(self):
        """Loads configuration and initializes services based on validity."""
        logging.info("Loading configuration and initializing services...")
        try:
            # Ensure config dir exists (moved from main.py startup)
            from turbo_sync.main import ensure_config_dir
            if not ensure_config_dir():
                 # Critical error, cannot proceed. Alert shown by ensure_config_dir.
                 # Maybe disable all menu items except Quit and Settings?
                 self.status_item.title = "Status: Config Dir Error"
                 self._disable_features() # Disable most features
                 return # Stop initialization

            # --- Add this line ---
            self.cleanup_syncthing() # Ensure any old instances are stopped first
            time.sleep(1) # Add a small delay to allow OS to release ports
            # --- End added line ---

            logging.debug(f"Loading configuration using path: {USER_ENV_PATH}")
            self.config = load_config(dotenv_path=USER_ENV_PATH) # load_config now always returns a dict

            if self.config and self.config.get('is_valid'):
                logging.info("Configuration loaded and valid. Initializing features.")
                self.status_item.title = "Status: Initializing..." # Start with initializing status
                self._enable_and_start_features()
            else:
                # Config is missing or invalid
                config_message = self.config.get('validation_message', "Configuration required.")
                logging.warning(f"Configuration invalid or missing: {config_message}")
                self.status_item.title = "Status: Configuration Required"
                self._disable_features()
                # Show notification prompting user to configure
                rumps.notification(
                    "TurboSync Setup",
                    "Configuration Needed",
                    "Please configure TurboSync via the Settings menu.",
                    sound=True
                )

        except Exception as e:
            logging.exception(f"Critical error during initialization: {e}")
            self.status_item.title = "Status: Initialization Error"
            self._disable_features() # Disable features on error
            rumps.notification(
                "TurboSync Critical Error",
                "Initialization Failed",
                f"An error occurred: {str(e)}",
                sound=True
            )

    def _enable_and_start_features(self):
        """Enables menu items and starts background services when config is valid."""
        logging.info("Enabling features and starting services...")

        # Enable menu items
        self.update_config_item.set_callback(self.update_syncthing_config_task)
        self.status_dashboard_item.set_callback(self.show_status_panel)
        self.watch_toggle.set_callback(self.toggle_file_watching)

        # Schedule the config update task
        schedule.clear() # Clear any previous schedules
        schedule.every(self.config['sync_interval']).minutes.do(self.scheduled_config_update)
        self._start_scheduler_thread() # Start scheduler thread if not running

        # Set up file watcher if enabled
        self.setup_file_watcher() # This handles enabling/disabling based on config

        # Start Syncthing Daemons (plural)
        self._start_syncthing_daemons_and_clients() # Updated for two instances

        # Start status polling (will be handled by _initialize_api_clients if successful)

        # Register cleanup function
        atexit.register(self.cleanup_syncthing)

        # Trigger initial config update check? Optional, but might be good.
        # Only run if config is valid, otherwise it will fail anyway
        if self.config and self.config.get('is_valid'):
            self.update_syncthing_config_task()
        # Initial status poll is triggered by _initialize_api_clients if successful


    def _disable_features(self):
        """Disables menu items and stops background services when config is invalid/missing."""
        logging.warning("Disabling features due to missing/invalid configuration.")

        # Disable menu items (except Settings, Logs, Quit)
        self.update_config_item.set_callback(None)
        self.status_dashboard_item.set_callback(None)
        self.watch_toggle.set_callback(None)
        self.watch_toggle.state = False # Ensure checkbox is off

        # Stop services
        self._stop_scheduler_thread()
        schedule.clear()
        self._stop_file_watcher()
        self._stop_status_poll_timer()
        self.cleanup_syncthing() # Stop Syncthing daemons if running

        # Clear API clients
        self.api_client_source = None
        self.api_client_dest = None

    def _start_syncthing_daemons_and_clients(self):
        """Generates initial configs, starts the TWO Syncthing daemons, and initializes their API clients."""
        if not self.config or not self.config.get('is_valid'):
            logging.warning("Cannot start Syncthing daemons: Configuration is invalid.")
            return

        # Get Syncthing executable path once
        from .syncthing_manager import get_syncthing_executable_path # Local import ok here
        syncthing_exe = get_syncthing_executable_path()
        if not syncthing_exe:
            logging.error("Syncthing executable not found. Cannot start daemons.")
            rumps.notification("TurboSync Error", "Syncthing Not Found", "Cannot start Syncthing.")
            return # Cannot proceed without the executable

        # --- Start Source Instance ---
        if self.syncthing_process_source and self.syncthing_process_source.poll() is None:
            logging.info("Syncthing source daemon already running.")
        else:
            logging.info("Preparing to start Syncthing source daemon...")
            api_addr_source = self.config.get('syncthing_api_address_source')
            gui_addr_source = self.config.get('syncthing_gui_address_source')
            if not api_addr_source or not gui_addr_source:
                 logging.error("Source Syncthing API or GUI address missing in config.")
            else:
                # 1. Generate config first
                logging.info("Generating initial config for source instance...")
                if generate_syncthing_config(syncthing_exe, SYNCTHING_CONFIG_DIR_SOURCE):
                    # 2. Start the daemon
                    logging.info("Attempting to start Syncthing source daemon...")
                    self.syncthing_process_source, error_msg = start_syncthing_daemon(
                        instance_id="source",
                        config_dir=SYNCTHING_CONFIG_DIR_SOURCE,
                        api_address=api_addr_source,
                        gui_address=gui_addr_source,
                        log_file=SYNCTHING_LOG_FILE_SOURCE
                    )
                    if not self.syncthing_process_source:
                        logging.error(f"Failed to start Syncthing source daemon: {error_msg}")
                        rumps.notification("TurboSync Error", "Syncthing Source Failed", f"Could not start: {error_msg}")
                    else:
                        logging.info(f"Syncthing source daemon started (PID: {self.syncthing_process_source.pid}).")
                else:
                    logging.error("Failed to generate initial config for source instance. Daemon not started.")
                    rumps.notification("TurboSync Error", "Syncthing Source Config Failed", "Could not generate initial config.")

        # --- Start Destination Instance ---
        if self.syncthing_process_dest and self.syncthing_process_dest.poll() is None:
            logging.info("Syncthing destination daemon already running.")
        else:
            logging.info("Preparing to start Syncthing destination daemon...")
            api_addr_dest = self.config.get('syncthing_api_address_dest')
            gui_addr_dest = self.config.get('syncthing_gui_address_dest')
            if not api_addr_dest or not gui_addr_dest:
                 logging.error("Destination Syncthing API or GUI address missing in config.")
            else:
                # 1. Generate config first
                logging.info("Generating initial config for destination instance...")
                if generate_syncthing_config(syncthing_exe, SYNCTHING_CONFIG_DIR_DEST):
                    # 2. Start the daemon
                    logging.info("Attempting to start Syncthing destination daemon...")
                    self.syncthing_process_dest, error_msg = start_syncthing_daemon(
                        instance_id="dest",
                        config_dir=SYNCTHING_CONFIG_DIR_DEST,
                        api_address=api_addr_dest,
                        gui_address=gui_addr_dest,
                        log_file=SYNCTHING_LOG_FILE_DEST
                    )
                    if not self.syncthing_process_dest:
                        logging.error(f"Failed to start Syncthing destination daemon: {error_msg}")
                        rumps.notification("TurboSync Error", "Syncthing Dest Failed", f"Could not start: {error_msg}")
                    else:
                        logging.info(f"Syncthing destination daemon started (PID: {self.syncthing_process_dest.pid}).")
                else:
                    logging.error("Failed to generate initial config for destination instance. Daemon not started.")
                    rumps.notification("TurboSync Error", "Syncthing Dest Config Failed", "Could not generate initial config.")

        # --- Initialize API Clients (if daemons started) ---
        # This is called AFTER attempting to start the daemons.
        # It will retrieve the API keys which should now exist thanks to --generate.
        self._initialize_api_clients()

    def _initialize_api_clients(self):
        """Initializes the Syncthing API clients for both instances."""
        if not self.config or not self.config.get('is_valid'):
            logging.warning("Cannot initialize API clients: Configuration invalid.")
            self.api_client_source = None
            self.api_client_dest = None
            self._stop_status_poll_timer()
            return

        # --- Initialize Source Client ---
        api_addr_source = self.config.get('syncthing_api_address_source')
        api_key_source = None
        # --- Add logging before the check ---
        source_process_status = "Not Set"
        source_poll_result = "N/A"
        if self.syncthing_process_source:
            source_process_status = "Set"
            try:
                source_poll_result = self.syncthing_process_source.poll()
            except Exception as e:
                 source_poll_result = f"Error polling: {e}"
        logger.debug(f"Checking Source Syncthing process before API key retrieval: Process={source_process_status}, Poll={source_poll_result}")
        # --- End added logging ---
        if self.syncthing_process_source and self.syncthing_process_source.poll() is None:
            logger.info("Attempting to retrieve API key from Source Syncthing config.xml...")
            # time.sleep(1) # Removed - get_api_key_from_config now handles retries
            api_key_source = get_api_key_from_config(config_dir=SYNCTHING_CONFIG_DIR_SOURCE)

        if api_key_source and api_addr_source:
            try:
                self.api_client_source = SyncthingApiClient(api_key=api_key_source, address=api_addr_source)
                logging.info("Source Syncthing API client initialized successfully.")
            except Exception as api_e:
                logging.error(f"Failed to initialize Source Syncthing API client: {api_e}")
                rumps.notification("TurboSync Error", "Source API Error", f"Could not connect: {api_e}")
                self.api_client_source = None
        else:
            if not api_key_source:
                logging.error("Source Syncthing API key not found in config.xml or daemon not running.")
                rumps.notification("TurboSync Warning", "Source API Key Missing", "Cannot connect to source Syncthing.")
            if not api_addr_source:
                 logging.error("Source Syncthing API address missing in config.")
            self.api_client_source = None

        # --- Initialize Destination Client ---
        api_addr_dest = self.config.get('syncthing_api_address_dest')
        api_key_dest = None
        # --- Add logging before the check ---
        dest_process_status = "Not Set"
        dest_poll_result = "N/A"
        if self.syncthing_process_dest:
            dest_process_status = "Set"
            try:
                dest_poll_result = self.syncthing_process_dest.poll()
            except Exception as e:
                 dest_poll_result = f"Error polling: {e}"
        logger.debug(f"Checking Dest Syncthing process before API key retrieval: Process={dest_process_status}, Poll={dest_poll_result}")
        # --- End added logging ---
        if self.syncthing_process_dest and self.syncthing_process_dest.poll() is None:
            logger.info("Attempting to retrieve API key from Destination Syncthing config.xml...")
            # time.sleep(1) # Removed - get_api_key_from_config now handles retries
            api_key_dest = get_api_key_from_config(config_dir=SYNCTHING_CONFIG_DIR_DEST)

        if api_key_dest and api_addr_dest:
            try:
                self.api_client_dest = SyncthingApiClient(api_key=api_key_dest, address=api_addr_dest)
                logging.info("Destination Syncthing API client initialized successfully.")
            except Exception as api_e:
                logging.error(f"Failed to initialize Destination Syncthing API client: {api_e}")
                rumps.notification("TurboSync Error", "Dest API Error", f"Could not connect: {api_e}")
                self.api_client_dest = None
        else:
            if not api_key_dest:
                logging.error("Destination Syncthing API key not found in config.xml or daemon not running.")
                rumps.notification("TurboSync Warning", "Dest API Key Missing", "Cannot connect to destination Syncthing.")
            if not api_addr_dest:
                 logging.error("Destination Syncthing API address missing in config.")
            self.api_client_dest = None

        # --- Start Polling Timer (only if BOTH clients initialized) ---
        if self.api_client_source and self.api_client_dest:
            self._start_status_poll_timer()
        else:
            self._stop_status_poll_timer() # Ensure timer is stopped if one or both failed

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
        logging.debug("Setting up file watcher...")
        # Ensure config is loaded and valid before proceeding
        if not self.config or not self.config.get('is_valid'):
            logging.warning("Skipping file watcher setup: Configuration invalid or missing.")
            self._stop_file_watcher() # Ensure it's stopped if it was running
            self.watch_toggle.state = False
            self.watch_enabled = False
            self.watch_toggle.set_callback(None) # Disable toggle if config invalid
            return

        # Config is valid, proceed with setup based on config values
        self.watch_enabled = self.config.get('watch_local_files', False)
        local_dir_to_watch = self.config.get('local_dir')
        watch_delay = self.config.get('watch_delay_seconds', 2)

        # Update menu item state and ensure callback is set
        self.watch_toggle.state = self.watch_enabled
        self.watch_toggle.set_callback(self.toggle_file_watching) # Ensure callback is active

        # Stop existing watcher if running
        self._stop_file_watcher()

        # Only start watcher if enabled in config, fswatch is available, and local_dir is set
        if self.watch_enabled and is_fswatch_available() and local_dir_to_watch:
            try:
                logging.info(f"Starting file watcher for: {local_dir_to_watch}")
                self.file_watcher = FileWatcher(
                    local_dir_to_watch,
                    self.on_files_changed,
                    watch_delay
                )
                if self.file_watcher.start():
                    logging.info("File watcher started successfully.")
                    # Optional: Notify user watcher started
                    # rumps.notification("TurboSync", "File Watcher Started", f"Watching {local_dir_to_watch}", sound=False)
                else:
                    logging.error("Failed to start file watcher process.")
                    self.watch_toggle.state = False # Reflect failure in UI
                    self.watch_enabled = False
            except Exception as e:
                logging.error(f"Error initializing or starting file watcher: {e}")
                rumps.notification("TurboSync", "File Watcher Error", f"Could not start watcher: {str(e)}", sound=True)
                self.watch_toggle.state = False
                self.watch_enabled = False
        elif self.watch_enabled and not is_fswatch_available():
            logging.warning("fswatch not available but file watching is enabled in config.")
            rumps.notification("TurboSync", "fswatch Not Found", "Install fswatch for file watching: brew install fswatch", sound=True)
            self.watch_toggle.state = False # Cannot enable
            self.watch_enabled = False
        elif self.watch_enabled and not local_dir_to_watch:
             logging.warning("File watching enabled but LOCAL_DIR is not set in config.")
             self.watch_toggle.state = False # Cannot enable
             self.watch_enabled = False
        else:
            logging.info("File watching is disabled in configuration.")
            self.watch_toggle.state = False
            self.watch_enabled = False

    def _stop_file_watcher(self):
        """Stops the file watcher if it's running."""
        if self.file_watcher:
            logging.info("Stopping file watcher...")
            try:
                self.file_watcher.stop()
                logging.info("File watcher stopped.")
            except Exception as e:
                logging.error(f"Error stopping file watcher: {e}")
            self.file_watcher = None

    def on_files_changed(self):
        """Callback for when files change (likely triggers config update)"""
        logging.debug("File changes detected by fswatch")
        # Trigger a Syncthing configuration update check, as a .livework file
        # might have been added or removed.
        logging.info("File changes detected, triggering Syncthing configuration update check.")
        rumps.notification(
            "TurboSync",
            "File Changes Detected",
            "Checking Syncthing configuration...",
            sound=False
        )
        self.update_syncthing_config_task(None) # Trigger the config update task

    @rumps.clicked("Enable File Watching") # Keep decorator
    def toggle_file_watching(self, sender):
        """Toggle file watching on/off via the menu item."""
        # This action should save the setting and then re-run setup_file_watcher
        current_state = sender.state # State before the click
        new_state_bool = not current_state
        new_state_str = 'true' if new_state_bool else 'false'
        logging.info(f"Toggling file watching via menu. New desired state: {new_state_bool}")

        # Check dependencies/config before enabling
        if new_state_bool: # Trying to enable
            if not is_fswatch_available():
                logging.warning("Cannot enable file watching, fswatch not available.")
                rumps.notification("TurboSync", "fswatch Not Found", "Install fswatch: brew install fswatch", sound=True)
                sender.state = False # Keep it off
                return
            # Check if config is valid and local_dir is set
            if not self.config or not self.config.get('is_valid') or not self.config.get('local_dir'):
                logging.warning("Cannot enable file watching, configuration invalid or LOCAL_DIR not set.")
                rumps.notification("TurboSync", "Configuration Required", "Set Local Directory in Settings and ensure config is valid to enable watching.", sound=True)
                sender.state = False # Keep it off
                return

        # Save the new setting
        # Use the internal save function to only update this key
        if self._save_settings_internal({'WATCH_LOCAL_FILES': new_state_str}):
            logging.info(f"Successfully saved WATCH_LOCAL_FILES={new_state_str}")
            # Reload config to ensure internal state is consistent
            # Note: _save_settings_internal doesn't reload, but the main _save_settings does.
            # For consistency, let's reload here after the internal save.
            self.config = load_config(dotenv_path=USER_ENV_PATH)
            # Re-run the setup function which will start/stop the watcher based on the new config
            self.setup_file_watcher()
            # Notify user
            rumps.notification("TurboSync", f"File Watching {'Enabled' if new_state_bool else 'Disabled'}", "", sound=False)
        else:
            logging.error("Failed to save file watching setting change.")
            # Revert the menu item state if save failed
            sender.state = current_state
            rumps.notification("TurboSync Error", "Save Failed", "Could not update file watching setting.", sound=True)

    # --- New task for updating Syncthing configuration ---
    # No decorator needed here if only called internally or via the MenuItem defined above
    def update_syncthing_config_task(self, sender=None):
        """Handles the execution of the Syncthing config update in a separate thread."""
        if self.is_updating_config:
            logging.warning("Config update task requested, but update is already in progress.")
            rumps.notification("Config Update In Progress", "", "Syncthing configuration update is already running.")
            return

        logger.info("Starting Syncthing configuration update task...")
        self.is_updating_config = True
        # Update UI to indicate config update is happening
        # Keep main status reflecting Syncthing state, maybe add temporary indicator?
        original_status_title = self.status_item.title
        self.status_item.title = "Status: Updating Config..."
        # Consider disabling the "Update Syncthing Config" menu item temporarily
        # self.menu["Update Syncthing Config"].set_callback(None) # Example

        # Define the target function for the background thread
        def config_update_thread_target():
            logger.info("Config update thread started.")
            # Ensure API clients are available before proceeding
            if not self.api_client_source or not self.api_client_dest:
                 logger.error("Cannot run config update: API clients not initialized.")
                 rumps.notification("TurboSync Error", "API Clients Missing", "Cannot update config.", sound=True)
                 # Need to finalize UI even on early exit
                 update_callback = functools.partial(
                     self._finalize_config_update_ui,
                     False, # success = False
                     "API clients not ready.",
                     original_status_title
                 )
                 rumps.Timer(update_callback, 0.1).start()
                 return # Exit thread target

            success = False
            message = "Config update failed."
            try:
                # Call the function from sync.py, passing the clients
                success, message = update_syncthing_configuration(self.api_client_source, self.api_client_dest)

                logger.info(f"Config update task completed in thread. Success: {success}, Message: {message}")
                # Show notification (safe from thread)
                rumps.notification(
                    "TurboSync",
                    "Syncthing Config Updated" if success else "Syncthing Config Update Failed",
                    message,
                    sound=not success # Sound on failure
                )

            except Exception as e:
                logger.error(f"Exception in config update thread target: {e}")
                logger.exception("Traceback:")
                success = False
                message = f"Error during config update: {e}"
                rumps.notification("TurboSync Config Error", message, "", sound=True)
            finally:
                # Schedule the final UI update on the main thread using a timer
                update_callback = functools.partial(
                    self._finalize_config_update_ui,
                    success,
                    message,
                    original_status_title # Pass back original title to restore if needed
                )
                # Use rumps.Timer for one-shot callback
                rumps.Timer(update_callback, 0.1).start()
                logger.debug("Scheduled final UI update from config update thread.")

        # Create and start the thread
        self.config_update_thread = threading.Thread(target=config_update_thread_target, daemon=True)
        self.config_update_thread.start()

    # --- New method to finalize UI updates on main thread after config update ---
    def _finalize_config_update_ui(self, success, message, original_status_title, timer):
        """Updates the UI on the main thread after config update completion."""
        # 'timer' object is passed automatically by rumps.Timer
        logger.info("Finalizing config update UI on main thread.")
        self.is_updating_config = False
        self.last_config_update_status = f"Last update: {time.strftime('%H:%M:%S')} - {'Success' if success else 'Failed'}"

        # Restore status title or trigger immediate poll?
        # Triggering a poll is better as the config change might affect status
        # Only poll if config is valid and BOTH API clients exist
        if self.config.get('is_valid') and self.api_client_source and self.api_client_dest:
             # Don't necessarily restore original title, let poll update it
             # self.status_item.title = original_status_title # Restore briefly while polling
             self._poll_syncthing_status() # Trigger immediate poll to reflect changes
        elif not self.config.get('is_valid'):
             self.status_item.title = "Status: Configuration Required" # Reset to config required status
        else:
             # Determine more specific status if possible
             source_running = self.syncthing_process_source and self.syncthing_process_source.poll() is None
             dest_running = self.syncthing_process_dest and self.syncthing_process_dest.poll() is None
             if not source_running and not dest_running:
                 self.status_item.title = "Status: Syncthing Stopped"
             elif not self.api_client_source or not self.api_client_dest:
                 self.status_item.title = "Status: Syncthing API Error" # If running but client failed
             else:
                 self.status_item.title = "Status: Syncthing Error" # Generic fallback

        # Re-enable the "Update Syncthing Config" menu item if it was disabled AND config is valid
        # update_item = self.menu.get("Update Syncthing Config") # Get by key/title
        # if update_item and update_item.callback is None:
        #    update_item.set_callback(self.update_syncthing_config_task)

        logger.info("Config update UI finalized.")

    # --- Progress Queue Handling Removed ---

    # --- Syncthing Status Polling ---
    def _start_status_poll_timer(self, interval=5): # Poll every 5 seconds
        """Starts the timer to periodically poll Syncthing status."""
        # Only start if config is valid and BOTH API clients exist
        if self.config.get('is_valid') and self.api_client_source and self.api_client_dest:
            if self.status_poll_timer is None:
                logger.info(f"Starting Syncthing status poll timer (interval: {interval}s).")
                self.status_poll_timer = rumps.Timer(self._poll_syncthing_status, interval)
                self.status_poll_timer.start()
            else:
                logger.debug("Status poll timer already running.")
        else:
             logger.warning("Cannot start status poll timer: Config invalid or one/both API clients not initialized.")
             self._stop_status_poll_timer() # Ensure it's stopped if conditions aren't met

    def _stop_status_poll_timer(self):
        """Stops the Syncthing status poll timer."""
        if self.status_poll_timer is not None:
            logger.info("Stopping Syncthing status poll timer.")
            self.status_poll_timer.stop()
            self.status_poll_timer = None

    def _poll_syncthing_status(self, timer=None):
        """Polls Syncthing API for status and updates UI."""
        if not self.api_client_source or not self.api_client_dest:
            logger.debug("Skipping status poll: One or both API clients not available.")
            # Update status to reflect API issue if needed
            source_running = self.syncthing_process_source and self.syncthing_process_source.poll() is None
            dest_running = self.syncthing_process_dest and self.syncthing_process_dest.poll() is None
            if not self.api_client_source and source_running:
                 self.status_item.title = "Status: Source API Error"
            elif not self.api_client_dest and dest_running:
                 self.status_item.title = "Status: Dest API Error"
            elif not source_running and not dest_running:
                 self.status_item.title = "Status: Syncthing Stopped"
            # else: # Both running but one client failed init earlier
            #    self.status_item.title = "Status: Syncthing API Error" # Already set potentially
            return

        logger.debug("Polling Syncthing status...")
        try:
            # Poll both instances
            statuses_source = self.api_client_source.get_all_folder_statuses()
            statuses_dest = self.api_client_dest.get_all_folder_statuses()

            # Combine statuses (simple approach: prioritize error/syncing states)
            # A more sophisticated approach might be needed depending on UI requirements
            # Merge, preferring source status if IDs conflict (though they shouldn't)
            combined_statuses = {**statuses_dest, **statuses_source}
            num_folders = len(combined_statuses) # Count unique folder IDs

            # Update the main status bar item (simple state for now)
            if combined_statuses:
                 # Check for errors or non-idle states across combined statuses
                 has_errors = any(SyncthingApiClient.parse_folder_status(s).get('error') for s in combined_statuses.values() if s)
                 is_syncing = any(SyncthingApiClient.parse_folder_status(s).get('state') not in ['idle', 'error', 'unknown', 'scanning'] for s in combined_statuses.values() if s)
                 is_scanning = any(SyncthingApiClient.parse_folder_status(s).get('state') == 'scanning' for s in combined_statuses.values() if s)

                 if has_errors:
                     self.status_item.title = f"Status: Syncthing Error ({num_folders} folders)"
                 elif is_syncing:
                     self.status_item.title = f"Status: Syncthing Syncing ({num_folders} folders)"
                 elif is_scanning:
                     self.status_item.title = f"Status: Syncthing Scanning ({num_folders} folders)"
                 else:
                     self.status_item.title = f"Status: Syncthing Idle ({num_folders} folders)"
            else:
                 # Handle case where status couldn't be fetched or no folders exist
                 # Check if processes are running
                 source_running = self.syncthing_process_source and self.syncthing_process_source.poll() is None
                 dest_running = self.syncthing_process_dest and self.syncthing_process_dest.poll() is None
                 if source_running and dest_running:
                     # Check if API clients are valid before assuming no folders
                     if self.api_client_source and self.api_client_dest:
                         self.status_item.title = "Status: Syncthing Running (No folders)"
                     else:
                         self.status_item.title = "Status: Syncthing Running (API Error)" # One or both clients failed init
                 else:
                     self.status_item.title = "Status: Syncthing Stopped"


            # Update the status panel if it's open
            if self.status_panel and self.status_panel.isVisible():
                self.status_panel.update_syncthing_display(combined_statuses) # Pass combined status

        except Exception as e:
            logger.error(f"Error during Syncthing status poll: {e}")
            self.status_item.title = "Status: API Error"
            # Consider stopping the timer if errors persist?
    # --- End Syncthing Status Polling ---

    # --- Update scheduled task ---
    # --- Scheduler Control ---
    def _start_scheduler_thread(self):
        """Starts the background scheduler thread if not already running."""
        if self.scheduler_thread is None or not self.scheduler_thread.is_alive():
            self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
            self.scheduler_thread.start()
            logging.info("Scheduler thread started.")
        else:
            logging.debug("Scheduler thread already running.")

    def _stop_scheduler_thread(self):
        """Signals the scheduler thread to stop (implementation depends on run_scheduler)."""
        # For the current run_scheduler, stopping the thread isn't clean.
        # We rely on daemon=True for exit. If cleaner stop is needed, run_scheduler needs modification.
        logging.info("Stopping scheduler thread (via daemon exit).")
        # If run_scheduler had a stop event: threading.Event().set()
        self.scheduler_thread = None # Clear reference

    def scheduled_config_update(self):
        """Run the scheduled Syncthing configuration update"""
        # Check if config is valid before running
        if self.config and self.config.get('is_valid'):
            logging.info("Scheduled Syncthing configuration update triggered.")
            self.update_syncthing_config_task()
        else:
            logging.debug("Skipping scheduled config update: Configuration invalid.")

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
            # Return defaults if file doesn't exist, so dialog shows defaults
            logging.warning(f"User settings file not found at {USER_ENV_PATH}. Providing defaults to dialog.")
            # Return a copy of the default config dictionary
            return DEFAULT_CONFIG.copy()
        try:
            # Load using dotenv_values which returns a dict
            loaded_settings = dotenv_values(USER_ENV_PATH)
            # Combine with defaults to ensure all keys are present for the dialog
            combined_settings = DEFAULT_CONFIG.copy()
            combined_settings.update(loaded_settings) # Override defaults with loaded values
            return combined_settings
        except Exception as e:
            logging.error(f"Error reading settings file {USER_ENV_PATH}: {e}")
            return DEFAULT_CONFIG.copy() # Return defaults on error

    def _save_settings_internal(self, settings_to_save):
        """Internal helper to save specific key-value pairs to the .env file."""
        logging.info(f"Saving specific settings to {USER_ENV_PATH}: {list(settings_to_save.keys())}")
        try:
            # Ensure the directory exists (redundant if ensure_config_dir ran, but safe)
            os.makedirs(USER_CONFIG_DIR, exist_ok=True)
            # Use set_key - it creates the file if it doesn't exist
            for key, value in settings_to_save.items():
                str_value = str(value) if value is not None else ''
                # Use quote_mode='never' unless value contains spaces or special chars?
                # For simplicity, let's try 'never' first. If issues arise, adjust.
                set_key(USER_ENV_PATH, key, str_value, quote_mode="never") # Creates/updates file
            logging.info(f"Successfully saved {len(settings_to_save)} key(s) to {USER_ENV_PATH}")
            return True
        except Exception as e:
            logging.exception(f"Error saving settings to {USER_ENV_PATH}: {e}")
            rumps.notification("TurboSync Error", "Save Failed", f"Could not save settings: {e}")
            return False

    def _save_settings(self, new_settings):
        """Saves all settings from the dialog back to the user's .env file and re-initializes."""
        logging.info(f"Saving all settings from dialog to {USER_ENV_PATH}")
        if self._save_settings_internal(new_settings):
            logging.info("Settings saved successfully. Re-initializing application state...")
            # --- Re-initialize based on the new settings ---
            # This will reload config, check validity, and start/stop/reconfigure services
            self._load_and_initialize()
            # --- End Re-initialization ---

            # --- Handle Start at Login (after re-initialization ensures config is loaded) ---
            if self.config and self.config.get('is_valid'): # Check validity again after reload
                 start_at_login = self.config.get('start_at_login', False)
                 self._set_login_item(start_at_login)
            else:
                 logging.warning("Cannot set login item status: Configuration is invalid after save.")
            # --- End Handle Start at Login ---

            return True
        else:
            # _save_settings_internal already showed notification
            return False

    def _check_restart_syncthing_daemon(self, new_settings):
        """Checks if Syncthing daemon needs restart based on settings changes.
           Called internally by _load_and_initialize after config reload."""
        # This logic is now effectively handled within _load_and_initialize
        # by stopping the old daemon (if any) and starting a new one if config is valid.
        # We might need finer control if only specific settings require a restart vs just API client re-init.
        # For now, the simpler approach in _load_and_initialize covers the main cases.
        logging.debug("Syncthing daemon restart check is handled by _load_and_initialize.")
        pass # Keep the method signature for now if needed later

    def _reinitialize_api_client(self, new_settings):
        """Re-initializes the API client after settings changes."""
        # This is now handled by _initialize_api_clients called from _load_and_initialize
        logging.debug("API client re-initialization handled by _initialize_api_clients.")
        pass


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


    # --- Custom Quit Handler ---
    def quit_app(self, sender=None):
        """Stops Syncthing daemon and then quits the application."""
        self._stop_status_poll_timer() # Stop polling first
        logging.info("Quit TurboSync requested.")
        self.cleanup_syncthing() # Call cleanup explicitly
        logging.info("Quitting rumps application.")
        rumps.quit_application()

    def cleanup_syncthing(self):
        """Stops the Syncthing daemons if they are running."""
        self._stop_status_poll_timer() # Ensure timer is stopped
        logging.info("Running Syncthing cleanup for both instances...")
        if self.syncthing_process_source:
            stop_syncthing_daemon(self.syncthing_process_source)
            self.syncthing_process_source = None # Clear the reference
        if self.syncthing_process_dest:
            stop_syncthing_daemon(self.syncthing_process_dest)
            self.syncthing_process_dest = None # Clear the reference

    # --- Status Panel Methods ---

    # --- Remove old _get_combined_status method ---
    # def _get_combined_status(self): ... (entire method removed)


    # Replace the existing show_status_panel method
    def show_status_panel(self, sender=None): # Allow calling without sender
        """Creates (if needed), connects, clears, and shows the StatusPanel."""
        # Ensure QApplication instance exists for PySide dialogs
        # Moved QApplication import here to avoid potential top-level conflicts
        from PySide6.QtWidgets import QApplication
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
                # --- Signal Connection Removed ---
                # self.sync_emitter.sync_progress_update.connect(self.status_panel.update_status)

                # Connect the panel's closed signal to reset our reference
                self.status_panel.closed.connect(self._status_panel_closed)
                logger.info("Status Panel created and signals connected.")
            except Exception as e:
                logger.exception("Failed to create StatusPanel instance.")
                rumps.notification("TurboSync Error", "Status Panel Error", f"Could not create panel: {e}")
                return # Don't proceed if creation failed
        else:
            # Instance exists, just ensure it's visible
            logger.info("Status Panel instance already exists. Showing it.")

        # --- Removed clear_status() call from here ---

        # Show and raise the window (whether new or existing)
        try:
            self.status_panel.show()
            self.status_panel.raise_() # Bring to front
            self.status_panel.activateWindow() # Ensure focus
        except Exception as e:
            logger.error(f"Error showing/activating status panel: {e}")
            rumps.notification("TurboSync Error", "Status Panel Error", f"Could not show panel: {e}")
        # Trigger an immediate poll/update when panel is shown
        self._poll_syncthing_status()

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
