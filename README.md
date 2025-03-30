# TurboSync

A macOS menubar application that automatically syncs files between your local machine and a remote server based on `.livework` file markers.

## Features

- Automatically detects directories with `.livework` files on the remote server
- Syncs those directories to your local machine using rsync
- **Real-time file watching**: Automatically syncs when local files change
- Configurable sync interval (default: every 5 minutes)
- Runs in the macOS menubar for easy access
- Provides notifications of sync status
- All configuration in a simple .env file - no command line arguments needed

## Requirements

- macOS (10.14 or later recommended)
- Python 3.7 or higher
- rsync (pre-installed on macOS)
- fswatch (optional, for file watching feature: `brew install fswatch`)
- SSH access to your remote server

## Installation

### Option 1: From Source

1. Clone this repository:
   ```
   git clone https://github.com/johnr24/TurboSync.git
   cd TurboSync
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Install fswatch (optional, for file watching):
   ```
   brew install fswatch
   ```
4. fill in the .env file with your remote server details


4. Build the macOS app:
   ```
   python build_app.py
   ```
   
   This will create a standalone macOS app in the `dist` directory and offer to install it to your Applications folder.

### Option 2: Manual Installation

1. Download the latest release from the [Releases](https://github.com/yourusername/TurboSync/releases) page
2. Move `TurboSync.app` to your Applications folder
3. Open the app - it will create a default configuration file if one doesn't exist

## Configuration

TurboSync uses a `.env` file for all configuration. When you first run the app, it will create a default `.env` file and open it for editing.

### Configuration Options

```
# Remote server configuration
REMOTE_USER=username
REMOTE_HOST=example.com
REMOTE_PORT=22
REMOTE_DIR=/path/to/remote/directory

# Local directory to sync to
LOCAL_DIR=/path/to/local/directory

# Sync interval in minutes
SYNC_INTERVAL=5

# Watch local files for changes
WATCH_LOCAL_FILES=true
WATCH_DELAY_SECONDS=2

# Rsync options
RSYNC_OPTIONS=-avz --delete --exclude=".*" --exclude="node_modules"
RSYNC_SSH_OPTIONS=-p ${REMOTE_PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
```

### Required Options

- `REMOTE_USER`: Your username on the remote server
- `REMOTE_HOST`: The hostname or IP address of the remote server
- `REMOTE_DIR`: The base directory on the remote server to scan for `.livework` files
- `LOCAL_DIR`: The local directory where files will be synced to

### Optional Options

- `REMOTE_PORT`: SSH port (default: 22)
- `SYNC_INTERVAL`: How often to sync in minutes (default: 5)
- `WATCH_LOCAL_FILES`: Enable or disable file watching (default: true)
- `WATCH_DELAY_SECONDS`: Delay between detecting changes and syncing, to prevent rapid syncs (default: 2)
- `RSYNC_OPTIONS`: Options to pass to rsync (default: `-avz --delete --exclude=".*" --exclude="node_modules"`)
- `RSYNC_SSH_OPTIONS`: Additional SSH options for rsync

## Usage

### Setting Up Remote Directories

1. On your remote server, create a `.livework` file in any directory you want to sync:
   ```
   touch /path/to/your/project/.livework
   ```

2. TurboSync will automatically detect and sync this directory and all its contents.

### Using the App

- TurboSync runs in your menubar with a sync icon
- Click the icon to access the menu
- Use "Sync Now" to manually trigger a sync
- Toggle "Enable File Watching" to turn automatic syncing on file changes on/off
- "View Logs" shows the log file for troubleshooting
- "Settings" opens the .env configuration file

## Advanced Usage

### File Watching

When file watching is enabled, TurboSync will monitor your local directory for changes and automatically sync when files are modified. This provides real-time bidirectional sync:

1. Remote to local: Happens on the schedule defined by `SYNC_INTERVAL`
2. Local to remote: Happens immediately when local files change

You can enable/disable file watching through the menu or the config file. If fswatch is not installed, TurboSync will notify you and disable the feature.

### Customizing Sync Options

You can customize the rsync options in your `.env` file:

```
RSYNC_OPTIONS=-avz --delete --exclude=".*" --exclude="node_modules" --exclude="*.log"
```

### Using SSH Keys

TurboSync uses your system's SSH configuration. Set up SSH keys for passwordless authentication:

```
ssh-copy-id username@remote-server
```

## Troubleshooting

- Check the log file through the "View Logs" menu option
- Ensure your SSH connection works correctly by testing: `ssh username@remote-server`
- Verify the remote directory path is correct
- Check that you have the necessary permissions on both local and remote directories
- If file watching isn't working, ensure fswatch is installed: `brew install fswatch`

## License

This project is licensed under the MIT License - see the LICENSE file for details.
