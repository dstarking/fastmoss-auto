#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m PyInstaller --noconfirm --clean --windowed --onedir --name FastMossAuto --osx-bundle-identifier com.dstarking.fastmossauto main.py
codesign --verify --deep --strict dist/FastMossAuto.app
ditto -c -k --sequesterRsrc --keepParent dist/FastMossAuto.app dist/FastMossAuto-macOS.zip
