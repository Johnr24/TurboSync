#!/usr/bin/env python3
from turbo_sync.watcher import is_fswatch_available, get_fswatch_config
from dotenv import load_dotenv
import os
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_remote_connection():
    """Test if we can connect to the remote host"""
    load_dotenv()
    
    remote_host = os.getenv('REMOTE_HOST')
    remote_user = os.getenv('REMOTE_USER')
    remote_port = os.getenv('REMOTE_PORT')
    
    logger.info(f"Testing connection to {remote_user}@{remote_host}:{remote_port}")
    
    try:
        result = subprocess.run(
            ['ssh', '-p', remote_port, f'{remote_user}@{remote_host}', 'echo "Connection successful"'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info("SSH connection successful")
            return True
        else:
            logger.error(f"SSH connection failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("SSH connection timed out")
        return False
    except Exception as e:
        logger.error(f"Error testing connection: {e}")
        return False

def test_local_directory():
    """Test if local directory exists and is accessible"""
    load_dotenv()
    
    local_dir = os.path.expanduser(os.getenv('LOCAL_DIR'))
    logger.info(f"Testing local directory: {local_dir}")
    
    if os.path.exists(local_dir):
        logger.info("Local directory exists")
        try:
            # Try to create a test file
            test_file = os.path.join(local_dir, '.test_write')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            logger.info("Local directory is writable")
            return True
        except Exception as e:
            logger.error(f"Local directory is not writable: {e}")
            return False
    else:
        logger.error("Local directory does not exist")
        return False

def test_fswatch():
    """Test if fswatch is working"""
    if is_fswatch_available():
        config = get_fswatch_config()
        logger.info(f"FSWatch config: {config}")
        return True
    else:
        logger.error("FSWatch is not available")
        return False

if __name__ == "__main__":
    logger.info("Starting tests...")
    
    logger.info("\nTesting local directory...")
    local_ok = test_local_directory()
    
    logger.info("\nTesting remote connection...")
    remote_ok = test_remote_connection()
    
    logger.info("\nTesting fswatch...")
    fswatch_ok = test_fswatch()
    
    logger.info("\nTest Results:")
    logger.info(f"Local Directory: {'✓' if local_ok else '✗'}")
    logger.info(f"Remote Connection: {'✓' if remote_ok else '✗'}")
    logger.info(f"FSWatch: {'✓' if fswatch_ok else '✗'}") 