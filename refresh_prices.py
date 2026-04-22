"""Refresh Opinet prices and rebuild index.html for GitHub Pages."""
import json, urllib.request, urllib.parse, time, re, sys
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
        r["gasoline_price_today"] = ""
        r["price_num"] = None
        r["trade_dt"] = ""
        r["trade_tm"] = ""
        continue
    detail = opinet("detailById.do", {"id": uid})
    if detail and "RESULT" in detail:
        oil = detail["RESULT"].get("OIL", [])
        for o in oil:
            if o.get("PRODCD") == "B027":
                r["gasoline_price_today"] = f"{o['PRICE']}원/L"
                r["price_num"] = int(o["PRICE"])
                r["trade_dt"] = detail["RESULT"].get("TRADE_DT", "")
                r["trade_tm"] = detail["RESULT"].get("TRADE_TM", "")
                break
        else:
            r["gasoline_price_today"] = ""
            r["price_num"] = None
    else:
        r["gasoline_price_today"] = ""
        r["price_num"] = None
    time.sleep(0.15)  # rate limit

# Save updated data
data_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

# Stats
yemin = [r for r in rows if r["currency"] == "여민전"]
cheongju = [r for r in rows if r["currency"] == "청주페이"]
yemin_total, yemin_priced = len(yemin), len([r for r in yemin if r.get("price_num") is not None])
cheongju_total, cheongju_priced = len(cheongju), len([r for r in cheongju if r.get("price_num") is not None])
print(f"여민전: {yemin_total}건 중 가격 {yemin_priced}건 / 청주페이: {cheongju_total}건 중 가격 {cheongju_priced}건")

# Rebuild HTML
html_rows = json.dumps(rows, ensure_ascii=False)

tmpl = Template((BASE / "template.html").read_text(encoding="utf-8"))
html = tmpl.substitute(
    html_rows=html_rows,
    yemin_total=yemin_total, yemin_priced=yemin_priced,
    cheongju_total=cheongju_total, cheongju_priced=cheongju_priced
)

(BASE / "index.html").write_text(html, encoding="utf-8")
print("index.html rebuilt successfully")
