@echo off
:: Chay uninstall voi quyen Admin
powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"%~dp0uninstall.ps1\"' -Verb RunAs"
