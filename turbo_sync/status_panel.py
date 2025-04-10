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
