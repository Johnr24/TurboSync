"""
Entry point for running TurboSync as a module (python -m turbo_sync)
"""

import multiprocessing
import os
import sys

# Suppress the RuntimeWarning messages about module imports
# This doesn't fix the underlying issue but stops the warnings from appearing
os.environ["PYTHONWARNINGS"] = "ignore::RuntimeWarning"

# Configure multiprocessing before importing any other modules
# This prevents the "found in sys.modules" warnings
if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        # Already set or not available, ignore
        pass
    
    # Import main module after multiprocessing configuration
    from .main import main
    main() 