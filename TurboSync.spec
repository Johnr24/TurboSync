
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['/Users/john/Documents/TurboSync/turbo_sync/main.py'],
    pathex=['/Users/john/Documents/TurboSync'],
    binaries=[],
    datas=[
        ('/Users/john/Documents/TurboSync/dist/.env.template', '.'), # Bundle the template instead of .env
        ('/Users/john/Documents/TurboSync/turbo_sync/icon.png', '.'),                                        # Include icon.png in the root
    ],
    hiddenimports=['plistlib'],
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
    argv_emulation=True,
    target_arch='arm64',
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
        'LSUIElement': True,  # Uncommented for menubar app
        'LSBackgroundOnly': False,
    },
)
