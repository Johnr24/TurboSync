from setuptools import setup, find_packages

setup(
    name="turbo_sync",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-dotenv",
        "rumps",
        "schedule",
        "fswatch",
    ],
    entry_points={
        "console_scripts": [
            "turbosync=turbo_sync.main:main",
        ],
    },
)
