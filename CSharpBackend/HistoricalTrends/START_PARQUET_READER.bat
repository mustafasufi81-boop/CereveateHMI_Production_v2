@echo off
echo ====================================
echo  Parquet Reader ^& Comparison Tool
echo ====================================
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo.
echo Starting Python Flask server...
echo.
python parquet_reader_app.py
pause
