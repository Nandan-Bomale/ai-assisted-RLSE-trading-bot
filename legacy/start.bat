@echo off
echo Starting MetaTrader 5...
start "" "C:\Program Files\MetaTrader 5\terminal64.exe"

echo Waiting for MT5 to initialize...
timeout /t 5 /nobreak > nul

echo Starting RLSE Algotrading Bot Server...
start "RLSE Algotrading Bot" cmd /k "python main.py"

echo Opening Dashboard in browser...
timeout /t 3 /nobreak > nul
start http://127.0.0.1:5000

echo Startup sequence complete!
