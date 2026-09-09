@echo off
cd /d %~dp0
if not exist venv (
    py -m venv venv
)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
set FLASK_APP=run.py
flask init-db
python run.py
pause
