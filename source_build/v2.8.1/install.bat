@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PUMA STOCK PRO SETUP
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
