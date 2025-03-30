import os
import sys
import logging

logger = logging.getLogger(__name__)

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        logger.debug(f"Running in PyInstaller bundle, base path: {base_path}")
    except AttributeError: # Changed from generic Exception to AttributeError
        # Not running in a bundle, use the script's directory structure
        # Go up two levels from utils.py to get the project root
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        logger.debug(f"Running from source, base path: {base_path}")

    resource_path = os.path.join(base_path, relative_path)
    logger.debug(f"Resolved resource path for '{relative_path}': {resource_path}")
    return resource_path
