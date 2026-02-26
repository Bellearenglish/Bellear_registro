@echo off
title Registro de Jornada - Bellear English

REM Ir a la carpeta correcta del proyecto
cd /d C:\Users\luis\Documents\registro_jornada\registro_jornada

REM Activar entorno virtual
call venv\Scripts\activate

REM Mostrar qué Registro_jornada.py se ejecuta (diagnóstico)
echo Ejecutando Registro_jornada.py desde:
cd

REM Lanzar Flask
start "" python Registro_jornada.py

REM Esperar 3 segundos
timeout /t 3 >nul

REM Abrir navegador
start http://127.0.0.1:5000