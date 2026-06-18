@echo off
echo Configurando JARVIS para iniciar automaticamente ao fazer login...
echo.

set TASK_NAME=JARVIS-Autostart
set BAT_PATH=%~dp0JARVIS.bat

schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%BAT_PATH%\"" ^
  /sc onlogon ^
  /rl limited ^
  /delay 0001:30 ^
  /f

if %errorlevel% equ 0 (
    echo [OK] JARVIS vai iniciar automaticamente 1 minuto e 30 segundos apos o login.
    echo      Para remover: schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo [ERRO] Falhou. Tente executar como Administrador.
)
echo.
pause
