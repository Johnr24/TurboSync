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
    """Find a required binary on the system PATH and return its path."""
    path = shutil.which(name)
    if not path:
        print(f"Error: Required binary '{name}' not found in system PATH.")
        print(f"Please install '{name}' and ensure it's accessible in your PATH.")
        sys.exit(1) # Exit if binary not found
    print(f"Found '{name}' at: {path}")
    return path

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
    print("Locating required binaries (fswatch, rclone)...")
    fswatch_path = find_required_binary("fswatch")
    rclone_path = find_required_binary("rclone")
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
    binaries=[
        ('{fswatch_path}', '.'), # Bundle fswatch into Contents/MacOS
        ('{rclone_path}', '.'),  # Bundle rclone into Contents/MacOS
    ],
    datas=[
        ('{os.path.join(script_dir, "turbo_sync", ".env.template")}', '.'), # Bundle the template from turbo_sync/
        ('{icon_path}', '.'),                                               # Include icon.png in the root
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
    entitlements_file=None,
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
    pyinstaller_command = ["pyinstaller", spec_file, "--noconfirm"]
    # The --noconfirm flag is now always added, so the conditional check is removed.
    # if args.non_interactive:
    #     pyinstaller_command.append("--noconfirm") # Add noconfirm flag if non-interactive
    subprocess.run(pyinstaller_command, check=True)

    # Removed redundant copy of .env to dist folder
    
    print("Build complete!")
    app_path = os.path.join(script_dir, "dist", "TurboSync.app")
    print(f"App is located at: {app_path}")
    
    # Fix permissions on the app in the dist folder
    fix_app_permissions(app_path)

    # Install and launch only if interactive and requested, AND sudo install is not specified
    if not args.non_interactive and not args.sudo_install:
        # Move app to Applications folder if requested
        install_response = input("Do you want to install TurboSync.app to your Applications folder? (y/n): ").strip().lower()
        if install_response == 'y':
            app_path = os.path.join(script_dir, "dist", "TurboSync.app")
            applications_path = "/Applications/TurboSync.app"

            # Remove existing app if it exists
            if os.path.exists(applications_path):
                print(f"Removing existing app at {applications_path}...")
                shutil.rmtree(applications_path)

            # Copy the app
            print(f"Installing app to {applications_path}...")
            shutil.copytree(app_path, applications_path)
            print(f"TurboSync app installed to {applications_path}")
            
            # Fix permissions and remove quarantine flag
            fix_app_permissions(applications_path)
            
            # Ask to launch the app
            launch_response = input("Do you want to launch TurboSync now? (y/n): ").strip().lower()
            if launch_response == 'y':
                print("Launching TurboSync...")
                subprocess.run(["open", applications_path])
    else:
        print("Skipping installation and launch prompts in non-interactive mode.")


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
        '--non-interactive',
        action='store_true',
        help='Run in non-interactive mode, suppressing prompts and using defaults or flags.'
    )
    parser.add_argument(
        '--install-fswatch',
        action='store_true',
        help='Attempt to install fswatch using Homebrew if not found (requires Homebrew). Only effective in non-interactive mode if Homebrew is present.'
    )
    parser.add_argument(
        '--sudo-install',
        action='store_true',
        help='Install app to /Applications using sudo (avoids permission issues)'
    )
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
