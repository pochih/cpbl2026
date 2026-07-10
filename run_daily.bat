@echo off
REM ============================================================
REM  CPBL 資料每日更新 (Windows 本機排程用)
REM  用「工作排程器 Task Scheduler」設定每日/每小時執行本檔。
REM ============================================================
cd /d "%~dp0"
python fetch_cpbl.py
echo [%date% %time%] cpbl_data.json updated>> update.log
