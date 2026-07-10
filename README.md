# ⚾ CPBL 2026 觀賽指南

參考 [2026 世足觀賽指南](https://pochih.github.io/worldcup2026/) 的設計概念，打造的**中華職棒 2026 賽季**觀賽網站。所有資料來自 **CPBL 官方網站**，並以腳本每日自動更新。

## 功能

- 🗓 **賽程月曆（4–9 月）**：每日場次、點日期看當天比賽、上/下月切換、回到今天
- ⚾ **比賽卡片**：
  - **先發投手**（賽前公布即顯示）
  - **先發首棒打者**（賽前補抓）
  - 已結束場次：比分、勝投／敗投／救援、單場 MVP
  - 延賽場次標示（含補賽日期）
- 📊 **球隊戰績**：上／下半季，依 CPBL 官方賽果**即時計算**（勝-敗-和、勝率、勝差、連勝敗）
- 🏆 **數據排行**：打擊 / 投手 TOP5（參考值）
- 🎽 **球隊介紹** / 📺 **轉播資訊**

## 檔案結構

```
cpbl/
├─ index.html          # 前端（讀取 cpbl_data.json）
├─ fetch_cpbl.py       # 資料抓取腳本（CPBL 官方）
├─ cpbl_data.json      # 產生的資料（自動更新）
├─ run_daily.bat       # Windows 本機排程用
└─ .github/workflows/update.yml   # GitHub Actions 自動更新
```

## 本機執行

```powershell
# 1) 安裝相依套件
pip install requests

# 2) 抓取最新資料
python fetch_cpbl.py          # 產生 cpbl_data.json

# 3) 啟動本機伺服器（index.html 以 fetch 讀取 JSON，需經 http）
python -m http.server 8899
# 開啟瀏覽器 → http://localhost:8899/index.html
```

> ⚠️ 直接以 `file://` 開啟 index.html 會因瀏覽器 CORS 限制無法載入 JSON，請務必透過 http 伺服器開啟。

## 每日自動更新 + 自動部署

需求對應：
| 需求 | 實作 |
|------|------|
| 抓真實賽程 4–9 月每天 | `getgamedatas` 一次取全季，篩選 4–9 月 |
| 每日更新明日先發投手 | 排程 feed 內含 `先發投手`；排程多次執行即更新 |
| 每日比賽前更新先發首位打序 | 對今日/明日場次補抓 `box/getlive` 的 `FirstMover` |
| 數據排行自動抓取 | `stats/recordall` 抓打擊5項+投手3項，救援成功由賽果統計 |

### 架構（重要）
> ⚠️ **CPBL 官網會封鎖雲端機房 IP（GitHub Actions 抓不到，會回傳擋頁）**，因此
> **資料抓取必須在可連線 CPBL 的本機（台灣網路）執行**；GitHub 端只負責網站自動部署。

```
本機（台灣網路）                         GitHub
┌─────────────────────┐   git push   ┌────────────────────┐
│ 工作排程器每日執行     │ ───────────▶ │ main 分支更新        │
│ run_daily.bat         │              │  ↓ 自動觸發          │
│  → fetch_cpbl.py      │              │ GitHub Pages 重新部署 │
│  → 產生 cpbl_data.json │              │  → 網站即時更新       │
│  → git commit & push  │              └────────────────────┘
└─────────────────────┘
```

### 設定 Windows 工作排程器（本機自動更新）
1. 開「工作排程器」→ 建立基本工作。
2. 觸發程序：每天，可加多個時間（如 08:00 / 12:00 / 17:00 / 21:00 —
   先發投手常於賽前一日公布、先發打序賽前約 1 小時公布）。
3. 動作：啟動程式 → 選擇本資料夾的 `run_daily.bat`。
4. 之後每次執行都會自動抓取最新資料並 push，GitHub Pages 會自動重新部署。

> 首次 push 需已設定好 git 認證（本機已用 `gh auth login` 或 git 憑證管理員登入）。

### 線上網址
GitHub Pages：<https://pochih.github.io/cpbl2026/>（push 後約 1 分鐘更新）

## 資料來源

- 中華職棒官方全球資訊網：<https://www.cpbl.com.tw/>
  - 賽程 / 先發投手：`POST /schedule/getgamedatas`
  - 先發打序 / Box：`POST /box/getlive`

本專案為非官方粉絲整理，數據以 CPBL 官網為準。
