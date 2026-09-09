#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-dev.txt

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name EQL-Inventory-Cleaner \
  eql_inventory_cleaner.py

echo
echo "Build complete: dist/EQL-Inventory-Cleaner"
