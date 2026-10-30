@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo PyInstaller kuruluyor...
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto hata
echo.
echo EXE olusturuluyor (dist\Nexus.exe)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name Nexus ^
  --collect-all sounddevice ^
  --collect-all google.genai ^
  main.py
if errorlevel 1 goto hata
echo.
echo Tamamlandi: dist\Nexus.exe
pause
exit /b 0
:hata
echo.
echo Islem basarisiz oldu.
pause
exit /b 1
