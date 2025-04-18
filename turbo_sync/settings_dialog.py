import logging
import sys
from collections import OrderedDict

import logging
import sys
from collections import OrderedDict

# --- PySide6 Imports ---
# Keep these imports specific to this file
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QToolTip, # Added QToolTip
    QCheckBox, QPushButton, QDialogButtonBox, QGroupBox, QSpinBox, QPlainTextEdit,
    QHBoxLayout, QFileDialog  # Added QHBoxLayout and QFileDialog
)
from PySide6.QtCore import Qt # Keep Qt if needed, Slot might not be

# --- PySide6 Settings Dialog ---
class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TurboSync Settings")
        self.setMinimumWidth(500) # Set a minimum width

        # --- Apply Rainbow Stylesheet ---
        rainbow_qss = """
QDialog {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 rgba(255, 200, 200, 150), /* Light Red */
                                      stop:0.2 rgba(255, 220, 180, 150), /* Light Orange */
                                      stop:0.4 rgba(255, 255, 200, 150), /* Light Yellow */
                                      stop:0.6 rgba(200, 255, 200, 150), /* Light Green */
                                      stop:0.8 rgba(200, 200, 255, 150), /* Light Blue */
                                      stop:1 rgba(230, 200, 255, 150)); /* Light Violet */
}

QGroupBox {
    font-weight: bold;
    background-color: rgba(255, 255, 255, 180); /* Semi-transparent white */
    border: 1px solid #CCCCCC;
    border-radius: 5px;
    margin-top: 10px;
    padding: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 3px;
    background-color: rgba(230, 230, 230, 200); /* Slightly transparent grey */
    border-radius: 3px;
    color: #111; /* Dark text for title */
}

QLabel {
    color: #222; /* Dark grey text */
    background-color: transparent; /* Ensure label background is transparent */
}

QLineEdit, QSpinBox, QPlainTextEdit {
    background-color: white;
    border: 1px solid #AAAAAA;
    border-radius: 3px;
    padding: 3px;
    color: #111;
}
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    background-color: #E0E0E0;
    border: 1px solid #B0B0B0;
    border-radius: 2px;
    width: 16px; /* Ensure buttons have some width */
}
QSpinBox::up-arrow, QSpinBox::down-arrow {
     width: 9px;
     height: 9px;
}
QSpinBox::up-arrow {
    image: url(PLACEHOLDER_UP_ARROW.png); /* Requires actual arrow images or use default */
}
QSpinBox::down-arrow {
    image: url(PLACEHOLDER_DOWN_ARROW.png); /* Requires actual arrow images or use default */
}


QCheckBox {
    color: #222; /* Ensure checkbox text is dark */
    background-color: transparent;
}
QCheckBox::indicator {
    width: 13px;
    height: 13px;
    border: 1px solid #888888;
    border-radius: 3px;
    background-color: white;
}
QCheckBox::indicator:checked {
    background-color: #5599FF; /* Blue checkmark background */
    border-color: #3377DD;
    /* You might need an image for the checkmark itself if the default isn't visible */
    /* image: url(checkmark.png); */
}


QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6f7fa, stop:1 #dadbde);
    border: 1px solid #b0b0b0;
    border-radius: 4px;
    padding: 5px 15px;
    color: #111; /* Dark text */
    min-width: 60px; /* Ensure buttons have some minimum width */
}
QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #e0e0e0);
    border-color: #888888;
}
QPushButton:pressed {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #dadbde, stop:1 #f6f7fa);
}
        """
        self.setStyleSheet(rainbow_qss)
        # --- End Apply Stylesheet ---

        self.current_settings = current_settings
        self.widgets = {} # To store references to input widgets

        # Main layout
        layout = QVBoxLayout(self)

        # --- Define Settings Structure (Label, Key, Type, Default) ---
        # Using OrderedDict to control the display order and group boxes
        # Defaults here should ideally match DEFAULT_CONFIG in sync.py after it's updated
        settings_layout = OrderedDict([
            ("Directory Paths", {
                "SOURCE_DIR": ("Source Directory (contains .livework):", QLineEdit, ""),
                "LOCAL_DIR": ("Local Directory (sync destination):", QLineEdit, ""),
            }),
            ("Sync Behavior", {
                "SYNC_INTERVAL": ("Config Check Interval (minutes):", QSpinBox, 5), # How often to check for new .livework folders
            }),
            ("Syncthing Instance (Source)", { # Group Box for Source Syncthing Daemon
                "SYNCTHING_API_ADDRESS_SOURCE": ("API Address:", QLineEdit, "127.0.0.1:28384"),
                "SYNCTHING_GUI_ADDRESS_SOURCE": ("GUI Address:", QLineEdit, "127.0.0.1:28385"),
                # API Key is auto-retrieved, no longer configured here
            }),
            ("Syncthing Instance (Destination)", { # Group Box for Destination Syncthing Daemon
                "SYNCTHING_API_ADDRESS_DEST": ("API Address:", QLineEdit, "127.0.0.1:28386"),
                "SYNCTHING_GUI_ADDRESS_DEST": ("GUI Address:", QLineEdit, "127.0.0.1:28387"),
                # API Key is auto-retrieved, no longer configured here
            }),
            # File watching monitors the SOURCE_DIR for .livework changes
            # to trigger Syncthing config updates for BOTH instances.
            # Keep this group separate for clarity.
            ("File Watching (Source Directory)", { # Keep for triggering config updates?
                "WATCH_LOCAL_FILES": ("Watch Local Files (for .livework changes):", QCheckBox, True), # Clarified purpose
                "WATCH_DELAY_SECONDS": ("Watch Delay (seconds):", QSpinBox, 2), # Use QSpinBox
            }),
            ("Application Behavior", {
                "START_AT_LOGIN": ("Start TurboSync at Login:", QCheckBox, False),
            }),
        ])

        # --- Create Widgets Dynamically ---
        for group_name, settings in settings_layout.items():
            group_box = QGroupBox(group_name)
            form_layout = QFormLayout()

            for key, (label_text, widget_type, default_value) in settings.items():
                current_value = self.current_settings.get(key)
                widget = widget_type()

                if isinstance(widget, QLineEdit):
                    widget.setText(current_value if current_value is not None else str(default_value))
                elif isinstance(widget, QCheckBox):
                    # Handle 'true'/'false' strings from .env
                    checked = str(current_value).lower() == 'true' if current_value is not None else default_value
                    widget.setChecked(bool(checked))
                elif isinstance(widget, QSpinBox):
                    widget.setMinimum(1) # Sensible minimum for intervals/processes/delay
                    widget.setMaximum(9999) # Generous maximum
                    try:
                        val = int(current_value) if current_value is not None else default_value
                        widget.setValue(val)
                    except (ValueError, TypeError):
                         widget.setValue(int(default_value)) # Fallback to default if conversion fails
                elif isinstance(widget, QPlainTextEdit):
                     widget.setPlainText(current_value if current_value is not None else str(default_value))
                     widget.setFixedHeight(80) # Set a fixed height for the text area

                self.widgets[key] = widget

                # --- Special handling for directory paths ---
                if key in ["LOCAL_DIR", "SOURCE_DIR"]:
                    browse_button = QPushButton("Browse...")
                    # Use a lambda to pass the specific line edit to the slot
                    browse_button.clicked.connect(lambda checked=False, le=widget: self._browse_directory(le))

                    hbox = QHBoxLayout()
                    hbox.addWidget(widget) # Add the QLineEdit
                    hbox.addWidget(browse_button) # Add the Browse button
                    form_layout.addRow(QLabel(label_text), hbox) # Add the hbox containing both
                else:
                    # Add tooltips for Syncthing fields
                    if key == "SYNCTHING_API_ADDRESS_SOURCE" or key == "SYNCTHING_API_ADDRESS_DEST":
                         widget.setToolTip("REST API address (e.g., 127.0.0.1:port). Ensure ports are unique.")
                    elif key == "SYNCTHING_GUI_ADDRESS_SOURCE" or key == "SYNCTHING_GUI_ADDRESS_DEST":
                         widget.setToolTip("Web GUI address (e.g., 127.0.0.1:port). Ensure ports are unique and different from API ports.")
                    # API Key fields removed
                    # Default behavior for other widget types
                    form_layout.addRow(QLabel(label_text), widget)

            group_box.setLayout(form_layout)
            layout.addWidget(group_box)

        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def _browse_directory(self, line_edit_widget):
        """Opens a directory selection dialog and updates the QLineEdit."""
        # Get the current path from the line edit, if any, to start the dialog there
        current_path = line_edit_widget.text()
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            current_path # Start browsing from the current path in the line edit
        )
        if directory: # If the user selected a directory (didn't cancel)
            line_edit_widget.setText(directory)

    def get_settings(self):
        """Retrieves the settings from the widgets."""
        new_settings = {}
        for key, widget in self.widgets.items():
            if isinstance(widget, QLineEdit):
                new_settings[key] = widget.text()
            elif isinstance(widget, QCheckBox):
                # Store as 'true'/'false' strings consistent with .env
                new_settings[key] = 'true' if widget.isChecked() else 'false'
            elif isinstance(widget, QSpinBox):
                new_settings[key] = str(widget.value()) # Store as string
            elif isinstance(widget, QPlainTextEdit):
                new_settings[key] = widget.toPlainText()

        return new_settings

# --- Standalone Function to Launch PySide6 Dialog ---
# Keep this function here for now, associated with the dialog it launches
def launch_pyside_settings_dialog(menubar_app, current_settings):
    """
    Handles the creation and execution of the PySide6 settings dialog.
    Accepts the menubar_app instance to call its save method directly.
    """
    logging.info("Executing launch_pyside_settings_dialog.")
    try:
        # Ensure QApplication instance exists
        app = QApplication.instance()
        if app is None:
            logging.debug("No QApplication instance found, creating one for settings dialog.")
            # Pass sys.argv if available, otherwise an empty list
            app = QApplication(sys.argv if hasattr(sys, 'argv') else [])


        dialog = SettingsDialog(current_settings)
        if dialog.exec():
            logging.info("Settings dialog accepted (Save clicked).")
            new_settings = dialog.get_settings()
            logging.debug(f"Attempting to save settings via menubar_app instance: {new_settings}")
            # Call the save method directly on the passed-in instance
            if hasattr(menubar_app, '_save_settings') and callable(menubar_app._save_settings):
                menubar_app._save_settings(new_settings)
            else:
                logging.error("Passed menubar_app object does not have a callable _save_settings method.")
        else:
            logging.info("Settings dialog rejected (Cancel clicked or closed).")

    except ImportError as ie:
         logging.error(f"PySide6 import error: {ie}. Please ensure PySide6 is installed.")
         # Cannot use rumps notification here easily
         print(f"ERROR: PySide6 import error: {ie}. Please ensure PySide6 is installed.", file=sys.stderr)
         # Optionally, try to show a basic system alert if possible? (platform-dependent)
    except Exception as e:
        logging.exception("An error occurred within launch_pyside_settings_dialog")
        # Cannot use rumps notification here easily
        print(f"ERROR: Could not open settings: {e}", file=sys.stderr)
