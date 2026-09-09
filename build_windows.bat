@echo off
setlocal

py -m pip install --upgrade pip
py -m pip install -r requirements-dev.txt

py -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name EQL-Inventory-Cleaner ^
  eql_inventory_cleaner.py

if errorlevel 1 exit /b %errorlevel%

echo.
echo Build complete: dist\EQL-Inventory-Cleaner.exe
pause
