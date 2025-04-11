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
    QProgressBar # Add this line
)
from PySide6.QtCore import Qt, Signal, Slot

logger = logging.getLogger(__name__)

class StatusPanel(QDialog):
    """A dialog window to display the sync status of multiple projects."""

    # Signal emitted when the dialog is closed
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TurboSync Status")
        self.setMinimumWidth(600)
        self.setMinimumHeight(300)
        self.setAttribute(Qt.WA_DeleteOnClose, False) # Keep instance around

        # --- UI Elements ---
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(["Project", "Status", "Progress", "Details"])
        self.table_widget.verticalHeader().setVisible(False) # Hide row numbers
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers) # Read-only
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)

        # Set column resize modes
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) # Project Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Status
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Progress
        header.setSectionResizeMode(3, QHeaderView.Stretch) # Details

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.table_widget)
        self.setLayout(layout)

        # Store project data internally to manage updates
        self._project_data = {} # {path: {"name": str, "status": str, "progress": int, "details": str}}

    @Slot(dict)
    def update_status(self, combined_status_data):
        """
        Updates the table with the latest status data.

        Args:
            combined_status_data (dict): A dictionary where keys are project paths
                                         and values are dicts containing status info
                                         (e.g., {'name': ..., 'status': ..., 'progress': ..., 'details': ...}).
        """
        logger.debug(f"StatusPanel received update data: {combined_status_data}")
        if not combined_status_data:
             self.table_widget.setRowCount(0) # Clear table if no data
             return

        # Update internal data store first
        self._project_data = combined_status_data

        # Update table view
        self.table_widget.setRowCount(len(self._project_data))
        self.table_widget.setSortingEnabled(False) # Disable sorting during update

        row = 0
        # Sort by project name for consistent display
        sorted_paths = sorted(self._project_data.keys(), key=lambda p: self._project_data[p].get('name', ''))
        for path in sorted_paths:
            data = self._project_data[path]
            project_name = data.get('name', os.path.basename(path))
            status = data.get('status', 'Unknown')
            progress = data.get('progress', None) # Can be None or int
            details = data.get('details', '')

            # Create items
            item_project = QTableWidgetItem(project_name)
            item_status = QTableWidgetItem(status)
            item_progress = QTableWidgetItem(f"{progress}%" if progress is not None else "---")
            item_details = QTableWidgetItem(details)

            # Set alignment for progress
            item_progress.setTextAlignment(Qt.AlignCenter)

            # Add items to table
            self.table_widget.setItem(row, 0, item_project)
            self.table_widget.setItem(row, 1, item_status)
            self.table_widget.setItem(row, 2, item_progress)
            self.table_widget.setItem(row, 3, item_details)

            row += 1

        self.table_widget.setSortingEnabled(True) # Re-enable sorting

    def closeEvent(self, event):
        """Override close event to hide the window and emit a signal."""
        logger.debug("StatusPanel close event triggered.")
        self.hide()
        self.closed.emit() # Emit signal so menubar knows it was closed
        event.ignore() # Ignore the event to prevent actual closing/deletion

# --- Main execution for testing ---
if __name__ == '__main__':
    # Example usage for testing the panel directly
    logging.basicConfig(level=logging.DEBUG)
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    panel = StatusPanel()

    # Example data
    test_data = {
        "/path/to/project_alpha": {"name": "Project Alpha", "status": "Syncing", "progress": 50, "details": ""},
        "/path/to/project_beta": {"name": "Project Beta", "status": "Success", "progress": None, "details": "5 files synced"},
        "/path/to/project_gamma": {"name": "Project Gamma", "status": "Failed", "progress": None, "details": "rsync error code 12"},
        "/path/to/project_delta": {"name": "Project Delta", "status": "Idle", "progress": None, "details": ""},
    }
    panel.update_status(test_data)
    panel.show()

    sys.exit(app.exec())
import sys
import logging
import os # Added os import for basename
import time # Add this line
from PySide6.QtWidgets import (
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QApplication,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, Slot

logger = logging.getLogger(__name__)

class StatusPanel(QDialog):
    """A dialog window to display the sync status of multiple projects."""

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
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(["Project", "Status", "Progress"])
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)
        self.table_widget.setSortingEnabled(True)

        # Set column resize modes
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) # Project Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Status
        header.setSectionResizeMode(2, QHeaderView.Stretch) # Progress Bar

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.table_widget)
        self.setLayout(layout)

    # Replace the existing update_status method with this one:
    @Slot(dict)
    def update_status(self, progress_data):
        """
        """Receives progress updates via signal and updates the table."""
        logger.debug(f"StatusPanel received update: {progress_data}")
        msg_type = progress_data.get('type')
        project_name = progress_data.get('project')
        # Use path as a unique key, fall back to project name if path missing
        remote_path = progress_data.get('path', project_name)

        if not remote_path: # Need a unique identifier
            logger.warning(f"Received progress update without path/project identifier: {progress_data}")
            return
        if not project_name: # Need a display name
            project_name = os.path.basename(remote_path) if remote_path else "Unknown"


        # Find existing row using remote_path stored in UserRole data
        row_index = -1
        for i in range(self.table_widget.rowCount()):
            name_item = self.table_widget.item(i, 0) # Project Name item is in column 0
            if name_item and name_item.data(Qt.UserRole) == remote_path:
                row_index = i
                break

        if row_index == -1: # New project entry
            # Disable sorting temporarily to avoid issues when adding rows/widgets
            self.table_widget.setSortingEnabled(False)
            row_index = self.table_widget.rowCount()
            self.table_widget.insertRow(row_index)

            # Column 0: Project Name (Store path in UserRole)
            name_item = QTableWidgetItem(project_name)
            name_item.setData(Qt.UserRole, remote_path)
            self.table_widget.setItem(row_index, 0, name_item)

            # Column 1: Status Text
            status_item = QTableWidgetItem("Starting...")
            self.table_widget.setItem(row_index, 1, status_item)

            # Column 2: Progress Bar
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setTextVisible(True)
            progress_bar.setAlignment(Qt.AlignCenter) # Center text
            self.table_widget.setCellWidget(row_index, 2, progress_bar)

            # Re-enable sorting
            self.table_widget.setSortingEnabled(True)

            # Initialize internal state
            self.project_status[remote_path] = {'status': 'starting', 'progress': 0, 'start_time': time.time()}
        else:
            # Row exists, get existing widgets/items
            status_item = self.table_widget.item(row_index, 1)
            progress_bar = self.table_widget.cellWidget(row_index, 2)
            # Ensure progress bar widget exists
            if not isinstance(progress_bar, QProgressBar):
                logger.error(f"Progress bar missing for row {row_index}, project {project_name}. Recreating.")
                progress_bar = QProgressBar()
                progress_bar.setRange(0, 100)
                progress_bar.setValue(0)
                progress_bar.setTextVisible(True)
                progress_bar.setAlignment(Qt.AlignCenter)
                self.table_widget.setCellWidget(row_index, 2, progress_bar)


        # --- Update Row Based on Message Type ---
        if msg_type == 'start':
            status_item.setText("Syncing...")
            progress_bar.setValue(0)
            progress_bar.setStyleSheet("") # Reset style in case it was error before
            self.project_status[remote_path]['status'] = 'syncing'
            self.project_status[remote_path]['start_time'] = time.time()

        elif msg_type == 'progress':
            percentage = progress_data.get('percentage', 0)
            # Only update if status is currently syncing
            if self.project_status.get(remote_path, {}).get('status') == 'syncing':
                status_item.setText("Syncing...") # Ensure status text is correct
                progress_bar.setValue(percentage)
                self.project_status[remote_path]['progress'] = percentage

        elif msg_type == 'end':
            success = progress_data.get('success', False)
            start_time = self.project_status.get(remote_path, {}).get('start_time', time.time())
            elapsed = time.time() - start_time
            if success:
                status_item.setText(f"Completed ({elapsed:.1f}s)")
                progress_bar.setValue(100)
                progress_bar.setStyleSheet("") # Reset style
                self.project_status[remote_path]['status'] = 'completed'
            else:
                error_msg = progress_data.get('error', 'Unknown error')
                status_item.setText(f"Failed ({elapsed:.1f}s)")
                status_item.setToolTip(f"Error: {error_msg}") # Show error on hover
                # Set progress bar style for error
                progress_bar.setStyleSheet("QProgressBar::chunk { background-color: red; }")
                progress_bar.setValue(100) # Show 100% but failed
                self.project_status[remote_path]['status'] = 'failed'
                self.project_status[remote_path]['error'] = error_msg

        elif msg_type == 'error': # Handle overall error messages
             # Find a way to display general errors, maybe add a label above the table?
             # For now, log it.
             logger.error(f"Received overall error message: {progress_data.get('message')}")

        elif msg_type == 'overall_end': # Handle overall completion
             # Maybe update window title or a status label?
             logger.info(f"Received overall sync end message: Success={progress_data.get('success')}")

        # Optional: Update overall status/progress bar based on self.project_status
        # self._update_overall_status()

    # Add this new method to the StatusPanel class
    def clear_status(self):
        """Clears the table and internal status."""
        # Disable sorting before clearing
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(0)
        # Re-enable sorting
        self.table_widget.setSortingEnabled(True)
        self.project_status = {}
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

    # Example data
    test_data = {
        "/path/to/project_alpha": {"name": "Project Alpha", "status": "Syncing", "progress": 50, "details": ""},
        "/path/to/project_beta": {"name": "Project Beta", "status": "Success", "progress": None, "details": "5 files synced"},
        "/path/to/project_gamma": {"name": "Project Gamma", "status": "Failed", "progress": None, "details": "rsync error code 12"},
        "/path/to/project_delta": {"name": "Project Delta", "status": "Idle", "progress": None, "details": ""},
    }
    panel.update_status(test_data)
    panel.show()

    sys.exit(app.exec())
import sys
import logging
import os # Added os import for basename
from PySide6.QtWidgets import (
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QApplication,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, Slot

logger = logging.getLogger(__name__)

class StatusPanel(QDialog):
    """A dialog window to display the sync status of multiple projects."""

    # Signal emitted when the dialog is closed by the user (e.g., clicking 'X')
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TurboSync Status")
        self.setMinimumWidth(600)
        self.setMinimumHeight(300)
        # Keep instance around when closed via 'X', hide it instead.
        # WA_DeleteOnClose is False by default for QDialogs unless specified otherwise.
        # self.setAttribute(Qt.WA_DeleteOnClose, False) # Explicitly false if needed

        # --- UI Elements ---
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(["Project", "Status", "Progress", "Details"])
        self.table_widget.verticalHeader().setVisible(False) # Hide row numbers
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers) # Read-only
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)
        self.table_widget.setSortingEnabled(True) # Enable sorting

        # Set column resize modes
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) # Project Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Status
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Progress
        header.setSectionResizeMode(3, QHeaderView.Stretch) # Details

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.table_widget)
        self.setLayout(layout)

        # Store project data internally to manage updates {path: {"name": str, "status": str, "progress": int, "details": str}}
        self._project_data = {}

    @Slot(dict)
    def update_status(self, combined_status_data):
        """
        Updates the table with the latest status data.

        Args:
            combined_status_data (dict): A dictionary where keys are project paths
                                         and values are dicts containing status info
                                         (e.g., {'name': ..., 'status': ..., 'progress': ..., 'details': ...}).
        """
        logger.debug(f"StatusPanel received update data: {combined_status_data}")

        # Update internal data store first
        self._project_data = combined_status_data if combined_status_data else {}

        # Update table view
        self.table_widget.setSortingEnabled(False) # Disable sorting during update
        self.table_widget.setRowCount(len(self._project_data))

        row = 0
        # Sort by project name for consistent display order if needed, though table sorting is enabled
        sorted_paths = sorted(self._project_data.keys(), key=lambda p: self._project_data[p].get('name', os.path.basename(p)))

        for path in sorted_paths:
            data = self._project_data[path]
            project_name = data.get('name', os.path.basename(path)) # Use basename as fallback name
            status = data.get('status', 'Unknown')
            progress = data.get('progress', None) # Can be None or int
            details = data.get('details', '')

            # Create items
            item_project = QTableWidgetItem(project_name)
            item_status = QTableWidgetItem(status)
            # Format progress nicely
            progress_text = f"{progress}%" if progress is not None else "---"
            item_progress = QTableWidgetItem(progress_text)
            item_details = QTableWidgetItem(details)

            # Set alignment for progress
            item_progress.setTextAlignment(Qt.AlignCenter)

            # Add items to table
            self.table_widget.setItem(row, 0, item_project)
            self.table_widget.setItem(row, 1, item_status)
            self.table_widget.setItem(row, 2, item_progress)
            self.table_widget.setItem(row, 3, item_details)

            row += 1

        self.table_widget.setSortingEnabled(True) # Re-enable sorting

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

    # Example data
    test_data = {
        "/path/to/project_alpha": {"name": "Project Alpha", "status": "Syncing", "progress": 50, "details": ""},
        "/path/to/project_beta": {"name": "Project Beta", "status": "Success", "progress": None, "details": "5 files synced"},
        "/path/to/project_gamma": {"name": "Project Gamma", "status": "Failed", "progress": None, "details": "rsync error code 12"},
        "/path/to/project_delta": {"name": "Project Delta", "status": "Idle", "progress": None, "details": ""},
    }
    panel.update_status(test_data)
    panel.show()

    sys.exit(app.exec())
