
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['/Users/john/Documents/TurboSync/turbo_sync/main.py'],
    pathex=['/Users/john/Documents/TurboSync'],
    binaries=[
        ('/opt/homebrew/bin/fswatch', '.'), # Bundle fswatch into Contents/MacOS
        ('/opt/homebrew/bin/rclone', '.'),  # Bundle rclone into Contents/MacOS
    ],
    datas=[
        ('/Users/john/Documents/TurboSync/turbo_sync/.env.template', '.'), # Bundle the template from turbo_sync/
        ('/Users/john/Documents/TurboSync/turbo_sync/icon.png', '.'),                                               # Include icon.png in the root
        ('/Users/john/Documents/TurboSync/turbo_sync/assets', 'assets'),   # Include any assets folder
    ],
    hiddenimports=['plistlib', 'AppKit', 'Foundation', 'Cocoa', 'rumps', 'objc'],
    hookspath=[],
    hooksconfig={},
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
    codesign_identity=None,
    entitlements_file=None,
    icon='/Users/john/Documents/TurboSync/TurboSync.icns',
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
    icon='/Users/john/Documents/TurboSync/TurboSync.icns',
    bundle_identifier='com.turbosync.app',
    info_plist={
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
        'LSEnvironment': {
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
        },
    },
)
