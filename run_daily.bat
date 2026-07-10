@echo off
REM ============================================================
REM  CPBL 資料每日更新 + 自動部署（本機排程用）
REM  流程：抓取最新資料 -> commit -> push -> GitHub Pages 自動重新部署
REM  用「工作排程器 Task Scheduler」設定每天多個時段執行本檔即可。
REM
REM  ※ 因 CPBL 官網封鎖雲端機房 IP，資料抓取必須在可連線 CPBL 的
REM    本機（台灣網路）執行；GitHub 端負責自動部署網站。
REM ============================================================
cd /d "%~dp0"

python fetch_cpbl.py
if errorlevel 1 (
  echo [%date% %time%] fetch failed>> update.log
  exit /b 1
)

git add cpbl_data.json
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "chore: update CPBL data %date% %time%"
  git push
  echo [%date% %time%] pushed>> update.log
) else (
  echo [%date% %time%] no change>> update.log
)
