# TurboSync 🏳️‍🌈🚀🏳️‍⚧️

<p align="center"><img src="turbo_sync/icon.png" alt="the turbo link icon which is a gay pride flag with the letter T in the middle of it, the icon has rounded corners much like any other app icon" width="128"></p>

A macOS menubar app that keeps local folders in sync with specific directories on a remote server. It looks for `.livework` files on the remote (via a mounted volume) and uses `rclone bisync` to synchronize those directories.

It also features optional real-time local file watching using `fswatch` to trigger immediate syncs when you save changes! 💾➡️☁️

## Key Features ✨

*   Automatic discovery of remote directories marked with `.livework`.
*   Bidirectional sync using `rclone bisync` (requires the remote path to be mounted locally).
*   Real-time sync on local changes (optional, requires `fswatch`).
*   Simple menubar interface for status and manual control.
*   Configuration via a `.env` file.

## Requirements 📋

*   macOS
*   Python 3.7+
*   `rclone` (Install: `brew install rclone`)
*   Locally mounted path for your remote server's file system (which can be local files or SMB/NFS share mounted in `/Volumes/`).
*   `fswatch` (Optional, for file watching: `brew install fswatch`)

## This repo should not be confused with sibiling project "TurboSort" 👀
<p align="center"><img src="readme/image.png" alt="The image depicts a David Mitchell from that Mitchell and Web Look, in the get me hennimore sketch, in a suit holding two signs one says Turbosync, Not TurboSort the other says, Turbo Sort not Turbo Sync, David is sitting down across from a table, a medium wide shot. set against an office background." width="512"></p>

Turbosort can be found here and is designed to work in tadem with colourstream or any S3 Server as a one way file transfer operation. 

TurboSort can be found here - https://github.com/johnr24/TurboSort

## Quick Install & Setup 🛠️

## Brew Install! 🍻

```
brew tap johnr24/turbosync
brew install turbosync
```
once that's done you can then do 
```
  ln -sfn "/opt/homebrew/opt/turbosync/TurboSync.app" /Applications/TurboSync.app
```
To link it to your app folder! 
## Manual Install 
1.  **Clone:**
    ```bash
    git clone https://github.com/johnr24/TurboSync.git
    cd TurboSync
    ```

2.  **Install Tools:**
    ```bash
    brew install rclone fswatch
    ```
    *(Skip `fswatch` if you don't need real-time local sync)*

3.  **Install Python Deps:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure:**
    *   Copy the template: `cp dist/.env.template .env`
    *   Edit `.env` and **carefully set `MOUNTED_VOLUME_PATH`** to the local path where your remote directory is mounted. Fill in other details like `REMOTE_USER`, `REMOTE_HOST`, `LOCAL_DIR`.

5.  **Build the App:**
    ```bash
    # Standard interactive build (with prompts)
    python build_app.py
    
    # OR build and install to Applications folder with sudo (recommended)
    python build_app.py --sudo-install
    ```
    *   This creates `TurboSync.app` in the `dist/` folder and can install it to `/Applications` with proper permissions.
    *   Using the `--sudo-install` flag is recommended to avoid permission issues when running from Applications.

6.  **Run:** Launch `TurboSync.app`. Check the menubar icon!

## Basic Usage 🖱️

1.  Ensure your remote volume is mounted locally at the path specified in `MOUNTED_VOLUME_PATH`.
2.  On the remote server (via the mounted path), create an empty `.livework` file inside any directory within the remote file structure you want TurboSync to manage.

    ```bash
    # Example on the mounted volume
    touch /Volumes/YourMount/path/to/project/.livework
    ```
3.  Run TurboSync. It will find the marked directories and start syncing them with corresponding folders in your `LOCAL_DIR`.
4.  Use the menubar icon to check status, sync manually, or toggle file watching.

Enjoy seamless syncing! 🎉

## Troubleshooting 🔧

### Permission Issues

If you encounter permission issues when copying the app to the Applications folder or when running it:

1. **Use the sudo-install flag:**
   ```bash
   python build_app.py --sudo-install
   ```
   This will build the app and install it to the Applications folder with the correct permissions.

2. **Manual fix for existing app:**
   ```bash
   # Fix permissions on the app bundle
   sudo chmod -R 755 /Applications/TurboSync.app
   sudo chmod +x /Applications/TurboSync.app/Contents/MacOS/TurboSync
   
   # Remove quarantine flag if present
   sudo xattr -d com.apple.quarantine /Applications/TurboSync.app
   ```

3. **App doesn't appear in menubar:**
   - Make sure the app has permissions to run as a background application
   - Check the logs at `~/Library/Logs/TurboSync/turbosync.log`
   - Ensure rclone and fswatch are installed and in your PATH

# License

A full copy of the license can be found in the github repo.
Please note Turbosync is a signtory of the 🏳️‍🌈 Pride Flag Covenant.
