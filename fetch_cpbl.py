#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CPBL 2026 資料抓取器 (fetch_cpbl.py)
-----------------------------------------------------------------
資料來源：中華職棒官方網站 https://www.cpbl.com.tw （非官方整理）

功能：
  1. 抓取 2026 全季一軍例行賽賽程（篩選 4~9 月），含真實比分、狀態、先發投手。
  2. 依「明日」與「今日」賽事，補抓 box/getlive 取得先發首位打序 (FirstMover)
     與（若已公布）完整先發打序。
  3. 依真實比分即時計算上/下半季球隊戰績（勝-敗-和、勝率、勝差、連勝敗）。
  4. 輸出 cpbl_data.json 供前端 index.html 讀取。

用法：
  python fetch_cpbl.py            # 產生 cpbl_data.json
建議以排程每日（或每小時）執行以達成「每日更新先發投手 / 賽前更新先發打序」。
"""
import requests, re, json, sys, datetime, time

BASE = "https://www.cpbl.com.tw"
YEAR = 2026
KIND = "A"                 # 一軍例行賽
MONTHS = range(4, 10)      # 4~9 月
TZ = datetime.timezone(datetime.timedelta(hours=8))  # 台北時間

TEAMS = {
    "ACN": {"name": "中信兄弟",           "abbr": "兄弟", "badge": "CTBC", "color": "#f5a800", "txt": "#000", "home": "台中洲際棒球場"},
    "ADD": {"name": "統一7-ELEVEn獅",     "abbr": "統一", "badge": "獅",   "color": "#f26924", "txt": "#fff", "home": "臺南市立棒球場"},
    "AJL": {"name": "樂天桃猿",           "abbr": "樂天", "badge": "猿",   "color": "#8b1a2e", "txt": "#fff", "home": "樂天桃園棒球場"},
    "AEO": {"name": "富邦悍將",           "abbr": "富邦", "badge": "悍",   "color": "#1b2e5a", "txt": "#fff", "home": "新莊棒球場"},
    "AAA": {"name": "味全龍",             "abbr": "味全", "badge": "龍",   "color": "#c8102e", "txt": "#fff", "home": "天母棒球場"},
    "AKP": {"name": "台鋼雄鷹",           "abbr": "台鋼", "badge": "鷹",   "color": "#00843d", "txt": "#fff", "home": "澄清湖棒球場"},
}

def tcode(full):  # ACN011 -> ACN
    return (full or "")[:3]

def new_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s

def get_token(s, page):
    r = s.get(BASE + page, timeout=25)
    m = re.search(r"RequestVerificationToken:\s*'([^']+)'", r.text)
    return m.group(1) if m else None

def fetch_schedule(s):
    """回傳全季賽事 list（原始 dict）。"""
    tok = get_token(s, "/schedule")
    r = s.post(BASE + "/schedule/getgamedatas",
               data={"calendar": f"{YEAR}/01/01", "location": "", "kindCode": KIND},
               headers={"RequestVerificationToken": tok, "Referer": BASE + "/schedule"},
               timeout=40)
    j = r.json()
    if not j.get("Success"):
        raise RuntimeError("schedule fetch failed")
    gd = j["GameDatas"]
    return json.loads(gd) if isinstance(gd, str) else gd

def derive_status(g, today):
    """回傳 (status, note)。status ∈ scheduled/final/postponed

    判斷準則（不倚賴不可靠的 PresentStatus）：
      - 比賽日 > 今日            → scheduled（未來場次）
      - 有勝投                    → final（已完成，含雨天保留成立）
      - 停賽標記 / 有保留補賽日   → postponed（延賽）
      - 過去日期且有比分          → final（含和局 / 提前結束）
      - 過去日期且無比分無結果    → postponed（未打）
      - 其餘（今日尚未開打）      → scheduled
    """
    date = g["GameDate"][:10]
    vs, hs = g.get("VisitingScore") or 0, g.get("HomeScore") or 0
    win = g.get("WinningPitcherName") or ""
    stop = str(g.get("IsGameStop", "0"))
    reserve = g.get("ReserveDate")

    if date > today:
        return "scheduled", ""
    if win:
        return "final", ""
    if stop == "1" or reserve:
        note = ("延賽 → " + reserve[:10].replace("-", "/") + " 補賽") if reserve else "延賽"
        return "postponed", note
    if date < today:
        if vs != 0 or hs != 0:
            return "final", ""          # 和局或提前結束
        return "postponed", ""          # 過去未打
    return "scheduled", ""              # 今日尚未開打

def fetch_firstmover(s, gsno):
    """補抓某場先發首位打序與（若有）完整先發。"""
    try:
        r = s.post(BASE + "/box/getlive",
                   data={"GameSno": str(gsno), "Year": str(YEAR), "KindCode": KIND},
                   headers={"Referer": BASE + "/box"}, timeout=25)
        j = r.json()
        det = json.loads(j["GameDetailJson"])[0]
        return {
            "awayFirst": det.get("VisitingFirstMover") or "",
            "homeFirst": det.get("HomeFirstMover") or "",
        }
    except Exception:
        return {}

LEADER_DEFS = {
    "batting": [("打擊率", "打擊率", True), ("全壘打", "全壘打", False),
                ("打點", "打點", False), ("安打", "安打", False), ("盜壘", "盜壘", False)],
    "pitching": [("防禦率", "防禦率", True), ("勝投", "勝場", False), ("奪三振", "奪三振", False)],
}

def fetch_record_table(s, position):
    """抓 RecordAll（規定打席/局數）完整列，回傳 (欄位名list, 球員list)。"""
    url = (f"{BASE}/stats/recordall?year={YEAR}&kindCode={KIND}"
           f"&gameType=01&position={position}&orderField=00&online=1")
    t = s.get(url, timeout=25).text
    names = re.findall(r'<th class="num[^"]*"(?:\s+data-sortby="\d*")?[^>]*>\s*([^<\n]+?)\s*<', t)
    rows = re.findall(r'<td class="sticky">(.*?)</td>(.*?)</tr>', t, re.S)
    players = []
    for sticky, rest in rows:
        team = re.search(r'TeamNo=([A-Z]{3})', sticky)
        name = re.search(r'/team/person[^>]*>\s*([^<]+?)\s*<', sticky)
        vals = re.findall(r'<td class="num[^"]*">\s*([^<]+?)\s*</td>', rest)
        if team and name:
            players.append((name.group(1), team.group(1), vals))
    return names, players

def top5(names, players, header, page_order=False):
    try:
        col = names.index(header)
    except ValueError:
        return []
    def num(v):
        try: return float(v)
        except Exception: return -1
    rows = players[:5] if page_order else sorted(
        players, key=lambda p: num(p[2][col]) if col < len(p[2]) else -1, reverse=True)[:5]
    return [[n, tm, vs[col]] for n, tm, vs in rows if col < len(vs)]

def fetch_leaders(s, games):
    out = {"batting": {}, "pitching": {}}
    bn, bp = fetch_record_table(s, "01")
    pn, pp = fetch_record_table(s, "02")
    for label, header, po in LEADER_DEFS["batting"]:
        out["batting"][label] = top5(bn, bp, header, po)
    for label, header, po in LEADER_DEFS["pitching"]:
        out["pitching"][label] = top5(pn, pp, header, po)
    # 救援成功：由賽程 CloserName 統計（後援投手不在規定局數榜）
    saves = {}
    for g in games:
        if g["status"] == "final" and g.get("save"):
            key = g["save"]
            tm = g["home"] if (g.get("hs", 0) or 0) > (g.get("as", 0) or 0) else g["away"]
            saves.setdefault(key, {"n": 0, "t": tm})
            saves[key]["n"] += 1
    sv = sorted(saves.items(), key=lambda kv: -kv[1]["n"])[:5]
    out["pitching"]["救援成功"] = [[nm, v["t"], str(v["n"])] for nm, v in sv]
    return out

def compute_standings(games):
    """依真實比分計算上/下半季戰績。GameSeasonCode: 1=上半季, 2=下半季"""
    halves = {"1": "上半季", "2": "下半季"}
    tbl = {h: {c: {"g": 0, "w": 0, "l": 0, "d": 0, "res": []} for c in TEAMS} for h in halves.values()}
    for g in games:
        if g["status"] != "final":
            continue
        h = halves.get(str(g.get("season", "")), None)
        if not h:
            continue
        a, hm = g["away"], g["home"]
        av, hv = g.get("as"), g.get("hs")
        if av is None or hv is None or a not in TEAMS or hm not in TEAMS:
            continue
        for c in (a, hm):
            tbl[h][c]["g"] += 1
        if av > hv:
            tbl[h][a]["w"] += 1; tbl[h][hm]["l"] += 1
            tbl[h][a]["res"].append("W"); tbl[h][hm]["res"].append("L")
        elif av < hv:
            tbl[h][hm]["w"] += 1; tbl[h][a]["l"] += 1
            tbl[h][hm]["res"].append("W"); tbl[h][a]["res"].append("L")
        else:
            tbl[h][a]["d"] += 1; tbl[h][hm]["d"] += 1
            tbl[h][a]["res"].append("T"); tbl[h][hm]["res"].append("T")

    def streak(res):
        if not res:
            return "-"
        last = res[-1]; n = 0
        for x in reversed(res):
            if x == last:
                n += 1
            else:
                break
        if last == "T":
            return "和" + str(n)
        return ("勝" if last == "W" else "敗") + str(n)

    out = {}
    for h, teams in tbl.items():
        rows = []
        for c, r in teams.items():
            if r["g"] == 0:
                continue
            pct = r["w"] / (r["w"] + r["l"]) if (r["w"] + r["l"]) else 0
            rows.append({"t": c, "g": r["g"], "w": r["w"], "l": r["l"], "d": r["d"],
                         "pct": pct, "streak": streak(r["res"])})
        rows.sort(key=lambda x: (-x["pct"], -x["w"]))
        if rows:
            lead = rows[0]
            for i, row in enumerate(rows):
                row["rk"] = i + 1
                gb = ((lead["w"] - row["w"]) + (row["l"] - lead["l"])) / 2
                row["gb"] = "-" if i == 0 else (str(int(gb)) if gb == int(gb) else f"{gb:.1f}")
                row["pct"] = f"{row['pct']:.3f}".replace("0.", ".") if row["pct"] else ".000"
        if rows:
            out[h] = rows
    return out

def main():
    s = new_session()
    print("抓取全季賽程 ...", file=sys.stderr)
    raw = fetch_schedule(s)
    today = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
    tomorrow = (datetime.datetime.now(TZ) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    games = []
    for g in raw:
        date = g["GameDate"][:10]
        mon = int(date[5:7])
        if mon not in MONTHS:
            continue
        a, hm = tcode(g["VisitingTeamCode"]), tcode(g["HomeTeamCode"])
        if a not in TEAMS or hm not in TEAMS:
            continue
        t = (g.get("PreExeDate") or g.get("GameDateTimeS") or "")[11:16]
        item = {
            "date": date, "no": g["GameSno"], "season": g.get("GameSeasonCode"),
            "away": a, "home": hm, "venue": g.get("FieldAbbe", ""), "time": t,
            "as": g.get("VisitingScore"), "hs": g.get("HomeScore"),
            "awayP": g.get("VisitingPitcherName") or "",   # 先發投手（客）
            "homeP": g.get("HomePitcherName") or "",       # 先發投手（主）
            "win": g.get("WinningPitcherName") or "", "lose": g.get("LoserPitcherName") or "",
            "save": g.get("CloserName") or "", "mvp": g.get("MvpName") or "",
        }
        st, note = derive_status(g, today)
        item["status"], item["note"] = st, note
        games.append(item)

    games.sort(key=lambda x: (x["date"], x["no"]))
    print(f"  4~9月共 {len(games)} 場", file=sys.stderr)

    # 針對今日 / 明日賽事補抓先發首位打序
    near = [g for g in games if g["date"] in (today, tomorrow)]
    for g in near:
        fm = fetch_firstmover(s, g["no"])
        if fm:
            g["awayFirst"] = fm.get("awayFirst", "")
            g["homeFirst"] = fm.get("homeFirst", "")
        time.sleep(0.4)
    print(f"  補抓 {len(near)} 場先發首位打序（今日/明日）", file=sys.stderr)

    standings = compute_standings(games)

    print("抓取數據排行 ...", file=sys.stderr)
    try:
        leaders = fetch_leaders(s, games)
    except Exception as e:
        print("  排行抓取失敗:", e, file=sys.stderr)
        leaders = {"batting": {}, "pitching": {}}

    data = {
        "updated": datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "today": today,
        "teams": TEAMS,
        "games": games,
        "standings": standings,
        "leaders": leaders,
        "source": "https://www.cpbl.com.tw/",
    }
    with open("cpbl_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("已輸出 cpbl_data.json", file=sys.stderr)

if __name__ == "__main__":
    main()
