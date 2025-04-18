import sys
import logging
from PySide6.QtWidgets import (
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QApplication,
    QSizePolicy,
    QProgressBar,
    QLabel # Add QLabel for overall status
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer # Add QTimer
import os # Add os import for basename
import time # Add time import
from datetime import datetime # For parsing timestamps
import math # For formatting bytes

logger = logging.getLogger(__name__)

class StatusPanel(QDialog):
    """A dialog window to display the sync status of multiple projects."""

    # Signal emitted when the dialog is closed
    # Signal emitted when the dialog is closed by the user (e.g., clicking 'X')
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TurboSync Status")
        self.setMinimumWidth(600)
        self.setMinimumHeight(300)
        # Keep instance around when closed via 'X', hide it instead.
        # self.setAttribute(Qt.WA_DeleteOnClose, False) # Default is False

        # Store status details internally
        self.project_status = {} # Add this line to store status details
        # Import helper here to avoid circular dependency if moved later
        from .syncthing_manager import SyncthingApiClient
        self._initUI() # Call a separate method for UI setup

    # Add this new method to the StatusPanel class
    def _initUI(self):
        """Initialize UI elements."""
        self.setWindowTitle("TurboSync Status")
        self.setMinimumWidth(600)
        self.setMinimumHeight(300)
        # Keep instance around when closed via 'X', hide it instead.
        # self.setAttribute(Qt.WA_DeleteOnClose, False) # Default is False

        # --- UI Elements ---
        self.table_widget = QTableWidget()
        # Change column count and labels
        self.table_widget.setColumnCount(5) # Increased columns
        self.table_widget.setHorizontalHeaderLabels(["Folder Label", "State", "Completion", "Size (Local/Global)", "Last Scan"])
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)
        self.table_widget.setSortingEnabled(True)

        # Set column resize modes
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) # Project Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # State
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Completion %
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Size
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Last Scan

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.table_widget)
        self.setLayout(layout)

    def _format_bytes(self, size_bytes):
        """Helper to format bytes into KB, MB, GB etc."""
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    def _format_timestamp(self, iso_timestamp):
        """Helper to format ISO timestamp into readable format."""
        if not iso_timestamp or iso_timestamp.startswith("0001"): # Handle zero time
            return "Never"
        try:
            # Parse ISO 8601 format, handling potential timezone offsets and fractional seconds
            dt_object = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            # Format as desired (e.g., YYYY-MM-DD HH:MM:SS)
            return dt_object.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"Could not parse timestamp: {iso_timestamp}")
            return iso_timestamp # Return original if parsing fails

    # Rename and refactor update_status
    # @Slot(dict) # Keep if called via signal, remove if called directly
    def update_syncthing_display(self, all_statuses):
        """Receives polled Syncthing status data and updates the table."""
        logger.debug(f"StatusPanel received Syncthing status update: {len(all_statuses)} folders")

        # Keep track of displayed folders to remove stale ones later
        displayed_folder_ids = set()

        # Disable sorting temporarily
        self.table_widget.setSortingEnabled(False)

        for folder_id, raw_status in all_statuses.items():
            if not raw_status:
                logger.warning(f"Received empty status for folder {folder_id}")
                continue

            displayed_folder_ids.add(folder_id)
            folder_label = raw_status.get('label', folder_id) # Use label if available

            # Parse the status
            # Use the static method from the manager (or copy it here)
            from .syncthing_manager import SyncthingApiClient # Local import ok here
            status = SyncthingApiClient.parse_folder_status(raw_status)

            # Find existing row or create a new one
            row_index = -1
            for i in range(self.table_widget.rowCount()):
                name_item = self.table_widget.item(i, 0) # Folder Label item is in column 0
                if name_item and name_item.data(Qt.UserRole) == folder_id:
                    row_index = i
                    break

            if row_index == -1: # New folder entry
                row_index = self.table_widget.rowCount()
                self.table_widget.insertRow(row_index)

                # Col 0: Folder Label (Store ID in UserRole)
                name_item = QTableWidgetItem(folder_label)
                name_item.setData(Qt.UserRole, folder_id)
                self.table_widget.setItem(row_index, 0, name_item)

                # Create items for other columns
                self.table_widget.setItem(row_index, 1, QTableWidgetItem()) # State
                self.table_widget.setItem(row_index, 2, QTableWidgetItem()) # Completion
                self.table_widget.setItem(row_index, 3, QTableWidgetItem()) # Size
                self.table_widget.setItem(row_index, 4, QTableWidgetItem()) # Last Scan

            # --- Update Row Items ---
            state_item = self.table_widget.item(row_index, 1)
            completion_item = self.table_widget.item(row_index, 2)
            size_item = self.table_widget.item(row_index, 3)
            scan_item = self.table_widget.item(row_index, 4)

            # Col 1: State
            state_text = status['state'].replace('-', ' ').capitalize()
            state_item.setText(state_text)
            if status['error']:
                state_item.setForeground(Qt.red)
                state_item.setToolTip(f"Error: {status['error']}")
            else:
                state_item.setForeground(Qt.black) # Reset color
                state_item.setToolTip("") # Clear tooltip

            # Col 2: Completion
            completion_item.setText(f"{status['completion']:.1f}%")
            completion_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Col 3: Size
            local_bytes = raw_status.get('localBytes', 0)
            global_bytes = raw_status.get('globalBytes', 0)
            size_item.setText(f"{self._format_bytes(local_bytes)} / {self._format_bytes(global_bytes)}")
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Col 4: Last Scan Time
            last_scan_time = raw_status.get('lastScan')
            scan_item.setText(self._format_timestamp(last_scan_time))

        # Remove rows for folders that are no longer reported
        rows_to_remove = []
        for i in range(self.table_widget.rowCount()):
            name_item = self.table_widget.item(i, 0)
            if name_item and name_item.data(Qt.UserRole) not in displayed_folder_ids:
                rows_to_remove.append(i)

        # Remove rows in reverse order to avoid index issues
        for i in sorted(rows_to_remove, reverse=True):
            self.table_widget.removeRow(i)

        # Re-enable sorting
        self.table_widget.setSortingEnabled(True)

    # Add this new method to the StatusPanel class
    def clear_status(self):
        """Clears the table and internal status."""
        # Disable sorting before clearing
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(0)
        # Re-enable sorting
        self.table_widget.setSortingEnabled(True)
        self.project_status = {} # Keep this if used elsewhere, otherwise remove
        logger.info("Status panel cleared.")

    def closeEvent(self, event):
        """Override close event to hide the window and emit a signal."""
        logger.debug("StatusPanel close event triggered (hiding window).")
        self.hide()
        self.closed.emit() # Emit signal so menubar knows it was closed/hidden
        event.ignore() # Ignore the event to prevent actual closing/deletion

# --- Main execution for testing ---
if __name__ == '__main__':
    # Example usage for testing the panel directly
    logging.basicConfig(level=logging.DEBUG)
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    panel = StatusPanel()

    # Example Syncthing status data (replace with actual polled data)
    test_statuses = {
        "folder-abc": {
            "label": "Project Alpha", "state": "idle", "globalBytes": 1024*1024*50, "localBytes": 1024*1024*50,
            "lastScan": "2023-10-27T10:00:00Z", "errors": 0, "pullErrors": []
        },
        "folder-def": {
            "label": "Project Beta", "state": "syncing", "globalBytes": 1024*1024*100, "localBytes": 1024*1024*75,
            "lastScan": "2023-10-27T10:05:00Z", "errors": 0, "pullErrors": []
        },
         "folder-xyz": {
            "label": "Project Gamma", "state": "error", "globalBytes": 1024*1024*20, "localBytes": 1024*1024*10,
            "lastScan": "2023-10-27T09:55:00Z", "errors": 1, "pullErrors": [{"time": "...", "error": "permission denied"}]
        },
    }
    panel.update_syncthing_display(test_statuses)
    panel.show()

    sys.exit(app.exec())
