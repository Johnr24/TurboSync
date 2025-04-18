#!/usr/bin/env python3
"""
Build script for TurboSync macOS app
"""

import os
import sys
import shutil
import subprocess
import argparse
import sys # Added sys import

def find_required_binary(name):
    """
    Find a required binary, prioritizing common user installation paths (like Homebrew)
    before falling back to the system PATH.
    """
    # Common Homebrew paths (Apple Silicon, Intel)
    preferred_paths = [
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
    ]

    # Check preferred paths first
    for preferred_path in preferred_paths:
        if os.path.exists(preferred_path) and os.access(preferred_path, os.X_OK):
            print(f"Found '{name}' at preferred location: {preferred_path}")
            return preferred_path

    # If not found in preferred paths, use shutil.which to search the system PATH
    path = shutil.which(name)
    if path:
        print(f"Found '{name}' using system PATH: {path}")
        # Check if the found path is SIP protected (like /usr/bin/rsync)
        if path.startswith("/usr/bin/") or path.startswith("/bin/") or path.startswith("/sbin/") or path.startswith("/usr/sbin/"):
             print(f"Warning: Found '{name}' at system path '{path}'. This might be SIP protected.")
             print(f"Consider installing '{name}' via Homebrew ('brew install {name}') for better bundling compatibility.")
             # We will still try to use it, but copying might fail later.
        return path
    else:
        # If still not found, exit with an error
        print(f"Error: Required binary '{name}' not found in preferred locations or system PATH.")
        print(f"Please install '{name}' (e.g., 'brew install {name}') and ensure it's accessible.")
        sys.exit(1) # Exit if binary not found

def ensure_icon_exists():
    """Ensure the icon exists for the app"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_dir = os.path.join(script_dir, "turbo_sync")
    icon_path = os.path.join(icon_dir, "icon.png")
    
    if not os.path.exists(icon_path):
        print("Creating app icon...")
        try:
            from PIL import Image, ImageDraw
            
            # Create a 128x128 transparent image
            img = Image.new('RGBA', (128, 128), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # First create a RGB flag background
            rainbow_colors = [
                (228, 3, 3),    # Red
                (255, 140, 0),  # Orange
                (255, 237, 0),  # Yellow
                (0, 128, 38),   # Green
                (0, 77, 255),   # Blue
                (117, 7, 135)   # Purple
            ]
            
            # Draw rainbow stripes
            stripe_height = 128 // len(rainbow_colors)
            for i, color in enumerate(rainbow_colors):
                y1 = i * stripe_height
                y2 = y1 + stripe_height
                draw.rectangle([(0, y1), (128, y2)], fill=color)
            
            # Draw a white "T" for TurboSync
            draw.rectangle([(50, 20), (78, 108)], fill=(255, 255, 255))
            draw.rectangle([(30, 20), (98, 40)], fill=(255, 255, 255))
            
            os.makedirs(icon_dir, exist_ok=True)
            img.save(icon_path)
            print(f"Created icon at {icon_path}")
        except Exception as e:
            print(f"Failed to create icon: {e}")
            # Create an empty placeholder
            os.makedirs(icon_dir, exist_ok=True)
            with open(icon_path, 'wb') as f:
                f.write(b'')
    
    # Create icns format for macOS
    icns_path = os.path.join(script_dir, "TurboSync.icns")
    if not os.path.exists(icns_path):
        try:
            # For macOS, we can use iconutil to create an icns file
            print("Creating icns icon for macOS...")
            
            # Copy the PNG to the right places
            temp_iconset = os.path.join(script_dir, "TurboSync.iconset")
            os.makedirs(temp_iconset, exist_ok=True)
            
            from PIL import Image
            img = Image.open(icon_path)
            
            # Create various sizes for the iconset
            sizes = [16, 32, 64, 128, 256, 512, 1024]
            for size in sizes:
                resized = img.resize((size, size), Image.LANCZOS)
                resized.save(os.path.join(temp_iconset, f"icon_{size}x{size}.png"))
                # Also save the @2x version
                if size * 2 <= 1024:
                    resized = img.resize((size * 2, size * 2), Image.LANCZOS)
                    resized.save(os.path.join(temp_iconset, f"icon_{size}x{size}@2x.png"))
            
            # Run iconutil to create the icns file
            subprocess.run(["iconutil", "-c", "icns", temp_iconset], check=True)
            
            # Clean up
            shutil.rmtree(temp_iconset)
            
            print(f"Created icns icon at {icns_path}")
        except Exception as e:
            print(f"Failed to create icns icon: {e}")
    
    return icon_path, icns_path

def build_app(args):
    """Build the macOS app using PyInstaller"""
    print("Building TurboSync macOS app...")
    
    # Fix permissions and remove quarantine flag
    def fix_app_permissions(app_path):
        """Fix permissions and remove quarantine flag from the app"""
        print(f"Fixing permissions and removing quarantine flag from {app_path}...")
        try:
            # Make the entire app bundle writable
            subprocess.run(["chmod", "-R", "u+w", app_path], check=False)
            
            # Make all executables executable
            subprocess.run(["find", app_path, "-type", "f", "-name", "*.so", "-exec", "chmod", "+x", "{}", ";"], check=False)
            subprocess.run(["find", app_path, "-type", "f", "-name", "*.dylib", "-exec", "chmod", "+x", "{}", ";"], check=False)
            
            # Make the main executable executable
            executable_path = os.path.join(app_path, "Contents/MacOS/TurboSync")
            if os.path.exists(executable_path):
                subprocess.run(["chmod", "+x", executable_path], check=False)
            
            # Remove quarantine flag
            subprocess.run(["xattr", "-d", "com.apple.quarantine", app_path], check=False)
            
            return True
        except Exception as e:
            print(f"Warning: Failed to fix permissions: {e}")
            return False
    
    # Ensure we're in the right directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Find required binaries needed for bundling
    print("Locating required binaries (fswatch, syncthing)...")
    fswatch_path = find_required_binary("fswatch")
    syncthing_path = find_required_binary("syncthing")
    print("Required binaries located successfully.")

    # Make sure dependencies are installed
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    
    # Add Pillow for icon creation
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow"], check=True)
    
    # Ensure icon exists and get its path
    icon_path, icns_path = ensure_icon_exists()
    
    # Create a spec file with precise resource handling
    spec_content = f'''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{os.path.join(script_dir, "turbo_sync", "main.py")}'],
    pathex=['{script_dir}'],
    binaries=[], # Keep binaries list empty for this test
    datas=[
        ('{os.path.join(script_dir, "turbo_sync", ".env.template")}', '.'), # Bundle the template from turbo_sync/
        ('{icon_path}', '.'),                                               # Include icon.png in the root
        # Binaries will be copied manually after build
    ],
    hiddenimports=['plistlib', 'AppKit', 'Foundation', 'Cocoa', 'rumps', 'objc'],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TurboSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # Reverted back to False for menubar app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity='-', # Apply ad-hoc signature during build
    entitlements_file='entitlements.plist', # Disable Library Validation
    icon='{icns_path}',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TurboSync',
)

app = BUNDLE(
    coll,
    name='TurboSync.app',
    icon='{icns_path}',
    bundle_identifier='com.turbosync.app',
    info_plist={{
        'CFBundleDisplayName': 'TurboSync',
        'CFBundleName': 'TurboSync',
        'CFBundleIdentifier': 'com.turbosync.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSUIElement': True,  # For menubar app
        'LSBackgroundOnly': False,
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'CFBundleDocumentTypes': [],
        'CFBundleExecutable': 'TurboSync',  # Must match the EXE name
        'NSRequiresAquaSystemAppearance': False,  # Support dark mode
        'LSApplicationCategoryType': 'public.app-category.utilities',
        'LSEnvironment': {{
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
        }},
    }},
)
'''
    
    # Write the spec file
    spec_file = os.path.join(script_dir, "TurboSync.spec")
    with open(spec_file, 'w') as f:
        f.write(spec_content)
    
    # Use PyInstaller with the spec file, always confirming removal of old build dirs
    pyinstaller_command = ["pyinstaller", spec_file, "--noconfirm"] # --noconfirm prevents prompts
    subprocess.run(pyinstaller_command, check=True)

    # --- Manually copy binaries after PyInstaller build ---
    app_path = os.path.join(script_dir, "dist", "TurboSync.app")
    macos_dir = os.path.join(app_path, "Contents", "MacOS")
    print(f"Manually copying binaries to {macos_dir}...")
    try:
        # Ensure MacOS directory exists (it should, but check just in case)
        os.makedirs(macos_dir, exist_ok=True)

        dest_fswatch = os.path.join(macos_dir, os.path.basename(fswatch_path))
        shutil.copy2(fswatch_path, dest_fswatch) # copy2 preserves metadata like permissions
        print(f"  - Copied {os.path.basename(fswatch_path)} to {macos_dir}")

        # Removed rsync copy
        # dest_rsync = os.path.join(macos_dir, os.path.basename(rsync_path))
        # shutil.copy2(rsync_path, dest_rsync)
        # print(f"  - Copied {os.path.basename(rsync_path)} to {macos_dir}")

        dest_syncthing = os.path.join(macos_dir, os.path.basename(syncthing_path))
        shutil.copy2(syncthing_path, dest_syncthing)
        print(f"  - Copied {os.path.basename(syncthing_path)} to {macos_dir}")
    except Exception as e:
        print(f"Error manually copying binaries: {e}")
        # Decide if build should fail here? For now, just warn and continue.
    # --- End manual copy ---

    # Removed redundant copy of .env to dist folder

    print("Build complete!")
    print(f"App is located at: {app_path}")

    # Explicitly set execute permissions for bundled binaries after build
    macos_dir = os.path.join(app_path, "Contents", "MacOS")
    fswatch_bundled_path = os.path.join(macos_dir, os.path.basename(fswatch_path))
    # rsync_bundled_path = os.path.join(macos_dir, os.path.basename(rsync_path)) # Removed rsync
    syncthing_bundled_path = os.path.join(macos_dir, os.path.basename(syncthing_path))

    print(f"Setting execute permissions for bundled binaries in {macos_dir}...")
    try:
        if os.path.exists(fswatch_bundled_path):
            subprocess.run(["chmod", "+x", fswatch_bundled_path], check=True)
            print(f"  - Set +x for {os.path.basename(fswatch_path)}")
        else:
             print(f"  - Warning: Bundled fswatch not found at {fswatch_bundled_path}")

        # Removed rsync permission setting
        # if os.path.exists(rsync_bundled_path):
        #      subprocess.run(["chmod", "+x", rsync_bundled_path], check=True)
        #      print(f"  - Set +x for {os.path.basename(rsync_path)}")
        # else:
        #      print(f"  - Warning: Bundled rsync not found at {rsync_bundled_path}")

        if os.path.exists(syncthing_bundled_path):
            subprocess.run(["chmod", "+x", syncthing_bundled_path], check=True)
            print(f"  - Set +x for {os.path.basename(syncthing_path)}")
       else:
            print(f"  - Warning: Bundled syncthing not found at {syncthing_bundled_path}")
    except Exception as e:
        print(f"Warning: Failed to set execute permissions for bundled binaries: {e}")


    # Interactive install/launch prompts removed. Use --sudo-install for installation.
    print("Build finished. Use --sudo-install flag to install to /Applications.")

    # Launch the app if requested via flag
    if args.launch:
        print("Launching TurboSync from build directory...")
        app_path_to_launch = os.path.join(script_dir, "dist", "TurboSync.app")
        if os.path.exists(app_path_to_launch):
            subprocess.run(["open", app_path_to_launch])
def install_with_sudo(app_path, applications_path):
    """Install the app to the Applications folder using sudo to avoid permission issues"""
    print(f"Installing {app_path} to {applications_path} using sudo...")
    try:
        # Remove existing app if it exists
        if os.path.exists(applications_path):
            print(f"Removing existing app at {applications_path}...")
            subprocess.run(["sudo", "rm", "-rf", applications_path], check=True)
        
        # Copy the app
        print(f"Copying app to {applications_path}...")
        subprocess.run(["sudo", "cp", "-R", app_path, applications_path], check=True)
        
        # Fix permissions
        print(f"Setting permissions...")
        subprocess.run(["sudo", "chmod", "-R", "755", applications_path], check=True)
        
        # Remove quarantine flag
        print(f"Removing quarantine flag...")
        subprocess.run(["sudo", "xattr", "-d", "com.apple.quarantine", applications_path], check=False)
        
        print(f"Successfully installed {app_path} to {applications_path}")
        return True
    except Exception as e:
        print(f"Error installing app: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the TurboSync macOS app.")
    parser.add_argument(
        '--install-fswatch',
        action='store_true',
        help='Attempt to install fswatch using Homebrew if not found (requires Homebrew). Only effective in non-interactive mode if Homebrew is present.'
    )
    parser.add_argument('--sudo-install', action='store_true', help='Install app to /Applications using sudo (avoids permission issues)')
    parser.add_argument('--launch', action='store_true', help='Launch the app from the dist directory after building.')
    parser.add_argument('--non-interactive', action='store_true', help='Run in non-interactive mode (for CI/automation, currently a no-op).')
    # Add flags for install/launch if needed for non-interactive local use,
    # but typically not desired for CI.
    # parser.add_argument('--install-app', action='store_true', help='Install app to /Applications (non-interactive).')
    # parser.add_argument('--launch-app', action='store_true', help='Launch app after build (non-interactive).')

    args = parser.parse_args()
    build_app(args)
    
    # If --sudo-install flag is provided, install the app using sudo
    if hasattr(args, 'sudo_install') and args.sudo_install:
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TurboSync.app")
        applications_path = "/Applications/TurboSync.app"
        install_with_sudo(app_path, applications_path)
