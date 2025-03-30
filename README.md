# TurboSync 🚀

![the turbo link icon which is a gay pride flag with the letter T in the middle of it, the icon has rounded corners much like any other app icon](turbo_sync/icon.png)

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



## Quick Install & Setup 🛠️

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
    python build_app.py
    ```
    *   This creates `TurboSync.app` in the `dist/` folder. Move it to `/Applications` if desired.

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
