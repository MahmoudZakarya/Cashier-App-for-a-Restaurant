@echo off
set PYTHONPATH=%cd%
set FLASK_APP=app.py
set ENV_FILE=.env.prod

echo Starting server...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --kiosk-printing http://127.0.0.1:8000

venv\Scripts\python.exe app.py
pause
