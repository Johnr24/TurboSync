#!/usr/bin/env python3
"""
Build script for TurboSync macOS app
"""

import os
import sys
import shutil
import subprocess

def check_fswatch():
    """Check if fswatch is installed, offer to install if not"""
    try:
        result = subprocess.run(
            ["which", "fswatch"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            print("\nfswatch is not installed, but recommended for file watching features.")
            response = input("Do you want to install fswatch using Homebrew? (y/n): ").strip().lower()
            if response == 'y':
                # Check if Homebrew is installed
                try:
                    subprocess.run(["brew", "--version"], capture_output=True, check=True)
                    # Install fswatch
                    print("Installing fswatch...")
                    subprocess.run(["brew", "install", "fswatch"], check=True)
                    print("fswatch installed successfully!")
                except (subprocess.SubprocessError, FileNotFoundError):
                    print("Error: Homebrew is not installed. Please install Homebrew first:")
                    print("  /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                    print("Then run: brew install fswatch")
            else:
                print("Skipping fswatch installation. File watching features will be disabled.")
        else:
            print("fswatch is already installed. File watching features will be available.")
    except Exception as e:
        print(f"Error checking fswatch: {str(e)}")

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

def build_app():
    """Build the macOS app using PyInstaller"""
    print("Building TurboSync macOS app...")
    
    # Ensure we're in the right directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Check if fswatch is installed
    check_fswatch()
    
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
    binaries=[],
    datas=[
        ('{os.path.join(script_dir, ".env")}', '.'),
        ('{icon_path}', '.'),
        ('{icon_path}', 'turbo_sync'),
    ],
    hiddenimports=['PIL._tkinter_finder', 'plistlib'],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch='arm64',
    codesign_identity=None,
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
        'LSUIElement': True,  # Makes the app appear only in the menubar
        'LSBackgroundOnly': False,
    }},
)
'''
    
    # Write the spec file
    spec_file = os.path.join(script_dir, "TurboSync.spec")
    with open(spec_file, 'w') as f:
        f.write(spec_content)
    
    # Use PyInstaller with the spec file
    subprocess.run(["pyinstaller", spec_file], check=True)
    
    # Copy the .env file to the dist directory if it exists
    env_path = os.path.join(script_dir, ".env")
    if os.path.exists(env_path):
        shutil.copy(env_path, os.path.join(script_dir, "dist"))
    
    print("Build complete!")
    print(f"App is located at: {os.path.join(script_dir, 'dist', 'TurboSync.app')}")
    
    # Move app to Applications folder if requested
    response = input("Do you want to install TurboSync.app to your Applications folder? (y/n): ").strip().lower()
    if response == 'y':
        app_path = os.path.join(script_dir, "dist", "TurboSync.app")
        applications_path = "/Applications/TurboSync.app"
        
        # Remove existing app if it exists
        if os.path.exists(applications_path):
            shutil.rmtree(applications_path)
        
        # Copy the app
        shutil.copytree(app_path, applications_path)
        print(f"TurboSync app installed to {applications_path}")
        
        # Ask to launch the app
        response = input("Do you want to launch TurboSync now? (y/n): ").strip().lower()
        if response == 'y':
            subprocess.run(["open", applications_path])

if __name__ == "__main__":
    build_app() 