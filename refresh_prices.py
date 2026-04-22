"""Refresh Opinet prices and rebuild index.html for GitHub Pages."""
import json, urllib.request, urllib.parse, time, re, sys
from datetime import datetime
from pathlib import Path
from string import Template

OPINET_KEY = sys.argv[1] if len(sys.argv) > 1 else "F260422158"
BASE = Path(__file__).parent

def opinet(endpoint, params):
    params["code"] = OPINET_KEY
    params["out"] = "json"
    url = f"https://www.opinet.co.kr/api/{endpoint}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(url, timeout=15)
            text = r.read().decode("utf-8", errors="replace")
            return json.loads(text)
        except Exception as e:
            if attempt == 2:
                print(f"  ERROR {endpoint}: {e}")
                return None
            time.sleep(1)

# Load existing station data
data_file = BASE / "station_data.json"
rows = json.loads(data_file.read_text(encoding="utf-8"))

# Collect uni_ids
uni_ids = [r["opinet_uni_id"] for r in rows if r.get("opinet_uni_id")]
print(f"Refreshing prices for {len(uni_ids)} stations...")

# Fetch prices in batches
for r in rows:
    uid = r.get("opinet_uni_id")
    if not uid:
        r.setdefault("gasoline_price_today", "")
        r.setdefault("price_num", None)
        r.setdefault("trade_dt", "")
        r.setdefault("trade_tm", "")
        continue
    old_price = r.get("gasoline_price_today", "")
    old_price_num = r.get("price_num")
    old_trade_dt = r.get("trade_dt", "")
    old_trade_tm = r.get("trade_tm", "")
    detail = opinet("detailById.do", {"id": uid})
    updated = False
    if detail and "RESULT" in detail:
        oil_rows = detail["RESULT"].get("OIL", [])
        oil0 = oil_rows[0] if oil_rows else None
        if oil0:
            for p in oil0.get("OIL_PRICE", []) or []:
                if p.get("PRODCD") == "B027" and p.get("PRICE"):
                    r["gasoline_price_today"] = f"{p['PRICE']}원/L"
                    r["price_num"] = int(p["PRICE"])
                    r["trade_dt"] = p.get("TRADE_DT", old_trade_dt)
                    r["trade_tm"] = p.get("TRADE_TM", old_trade_tm)
                    updated = True
                    break
    if not updated:
        r["gasoline_price_today"] = old_price
        r["price_num"] = old_price_num
        r["trade_dt"] = old_trade_dt
        r["trade_tm"] = old_trade_tm
    time.sleep(0.15)  # rate limit

for r in rows:
    td = str(r.get("trade_dt") or "").strip()
    tm = str(r.get("trade_tm") or "").strip().zfill(6)
    if td and tm:
        try:
            dt = datetime.strptime(td + tm, "%Y%m%d%H%M%S")
            r["updated_at_fmt"] = dt.strftime("%y.%m.%d %H:%M")
            r["_updated_at_dt"] = dt.isoformat()
        except Exception:
            r["updated_at_fmt"] = ""
            r["_updated_at_dt"] = ""
    else:
        r["updated_at_fmt"] = ""
        r["_updated_at_dt"] = ""

# Save updated data
data_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

# Rebuild HTML by replacing embedded rows array in template
html_rows = json.dumps(rows, ensure_ascii=False)
tmpl = (BASE / "template.html").read_text(encoding="utf-8")
html = re.sub(r"const rows=\[.*?\];", f"const rows={html_rows};", tmpl, count=1, flags=re.S)
(BASE / "index.html").write_text(html, encoding="utf-8")
print("index.html rebuilt successfully")
