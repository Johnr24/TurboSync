"""
TurboSync - A tool to sync files between local and remote servers
"""
import os
import logging

__version__ = "0.1.0"

# Ensure log directory exists before any imports or logging setup
os.makedirs(os.path.expanduser('~/Library/Logs/TurboSync'), exist_ok=True)

# Import main after ensuring log directory exists
from .main import main
