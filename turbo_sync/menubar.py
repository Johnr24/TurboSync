import os
import sys
import time
import threading
import logging
import rumps
import schedule
from dotenv import load_dotenv
from turbo_sync.sync import perform_sync, load_config # Absolute import
from turbo_sync.watcher import FileWatcher, is_fswatch_available, get_fswatch_config # Absolute import
from turbo_sync.utils import get_resource_path # Import from utils

class TurboSyncMenuBar(rumps.App):
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
            )
            logging.info("rumps.App initialization successful")
        except Exception as e:
            logging.error(f"Failed to initialize rumps.App: {e}")
            # Continue anyway with default icon
            super(TurboSyncMenuBar, self).__init__("TurboSync")
            logging.info("Initialized rumps.App with default icon")
        
        logging.debug("Setting up menu items")
        # Set up menu items
        self.menu = ["Sync Now", "View Logs", None, "Settings", None, "Quit"]
        
        # State variables
        self.syncing = False
        self.sync_thread = None
        self.status_item = None
        self.last_sync_status = "Never synced"
        self.file_watcher = None
        self.watch_enabled = False
        
        # Add status menu item
        self.status_item = rumps.MenuItem(f"Status: {self.last_sync_status}")
        self.menu.insert_before("Sync Now", self.status_item)
        
        # Add file watcher toggle
        self.watch_toggle = rumps.MenuItem("Enable File Watching")
        self.menu.insert_before("Settings", self.watch_toggle)
        
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
            rumps.notification(
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
                    rumps.notification(
                        "TurboSync",
                        "File Watcher Started",
                        f"Watching {fswatch_config['local_dir']} for changes",
                        sound=False
                    )
                else:
                    logging.error("Failed to start file watcher")
            except Exception as e:
                logging.error(f"Error starting file watcher: {e}")
                rumps.notification(
                    "TurboSync",
                    "File Watcher Error",
                    f"Could not start file watcher: {str(e)}",
                    sound=True
                )
                self.watch_toggle.state = False
                self.watch_enabled = False
        elif self.watch_enabled and not is_fswatch_available():
            logging.warning("fswatch not available but file watching is enabled")
            rumps.notification(
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
            rumps.notification(
                "TurboSync",
                "File Changes Detected",
                "Starting sync due to local file changes",
                sound=False
            )
            self.sync_now(None)
    
    @rumps.clicked("Enable File Watching")
    def toggle_file_watching(self, sender):
        """Toggle file watching on/off"""
        logging.debug(f"Toggle file watching: current state is {sender.state}")
        if sender.state:  # Currently enabled, disable it
            logging.info("Disabling file watching")
            sender.state = False
            self.watch_enabled = False
            
            if self.file_watcher:
                logging.debug("Stopping file watcher")
                self.file_watcher.stop()
                self.file_watcher = None
            
            rumps.notification(
                "TurboSync",
                "File Watching Disabled",
                "Will no longer sync on file changes",
                sound=False
            )
        else:  # Currently disabled, enable it
            if not is_fswatch_available():
                logging.warning("Cannot enable file watching, fswatch not available")
                rumps.notification(
                    "TurboSync",
                    "fswatch Not Found",
                    "Please install fswatch: brew install fswatch",
                    sound=True
                )
                return
            
            # Enable file watching
            logging.info("Enabling file watching")
            sender.state = True
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
                rumps.notification(
                    "TurboSync",
                    "File Watching Enabled",
                    f"Now watching {fswatch_config['local_dir']} for changes",
                    sound=False
                )
            else:
                logging.error("Failed to start file watcher")
                sender.state = False
                self.watch_enabled = False
    
    @rumps.clicked("Sync Now")
    def sync_now(self, _):
        logging.debug("Sync Now clicked")
        if self.syncing:
            logging.info("Sync already in progress, ignoring request")
            rumps.notification(
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
        
        try:
            success, message = perform_sync()
            
            if success:
                logging.info(f"Sync completed successfully: {message}")
                rumps.notification(
                    "TurboSync",
                    "Sync Completed",
                    message,
                    sound=False
                )
            else:
                logging.error(f"Sync failed: {message}")
                rumps.notification(
                    "TurboSync",
                    "Sync Failed",
                    message,
                    sound=True
                )
        except Exception as e:
            logging.exception(f"Exception during sync: {e}")
            success = False
            rumps.notification(
                "TurboSync",
                "Sync Error",
                f"An error occurred during sync: {str(e)}",
                sound=True
            )
        
        self.last_sync_status = f"Last sync: {time.strftime('%H:%M:%S')} - {'Success' if success else 'Failed'}"
        self.status_item.title = f"Status: {self.last_sync_status}"
        self.syncing = False
        logging.debug("Sync task completed")
    
    def scheduled_sync(self):
        """Run the scheduled sync if not already syncing"""
        logging.debug("Scheduled sync triggered")
        if not self.syncing:
            logging.info("Starting scheduled sync")
            self.sync_thread = threading.Thread(target=self.perform_sync_task)
            self.sync_thread.start()
        else:
            logging.debug("Skipping scheduled sync (sync already in progress)")
    
    @rumps.clicked("View Logs")
    def view_logs(self, _):
        logging.debug("View Logs clicked")
        log_path = os.path.expanduser('~/Library/Logs/TurboSync/turbosync.log')
        if os.path.exists(log_path):
            logging.info(f"Opening log file at: {log_path}")
            os.system(f"open {log_path}")
        else:
            logging.warning(f"Log file not found at: {log_path}")
            rumps.notification(
                "TurboSync",
                "Logs Not Found",
                "No log file exists yet.",
                sound=False
            )
    
    @rumps.clicked("Settings")
    def open_settings(self, _):
        logging.debug("Settings clicked")
        # Use get_resource_path to find the .env file correctly
        env_path = get_resource_path(".env")
        if env_path and os.path.exists(env_path):
            logging.info(f"Opening settings file at: {env_path}")
            # Use 'open -t' to open in the default text editor
            os.system(f"open -t \"{env_path}\"")
        else:
            logging.warning(f"Settings file not found at: {env_path}")
    
    @rumps.clicked("Quit")
    def quit_app(self, _):
        logging.info("Quit clicked, shutting down application")
        # Stop file watcher if running
        if self.file_watcher:
            logging.debug("Stopping file watcher")
            self.file_watcher.stop()
        
        logging.info("=== TurboSync Stopping ===")
        rumps.quit_application()

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
                rumps.notification(
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
