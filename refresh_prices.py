"""Refresh Opinet multi-fuel prices and rebuild index.html for GitHub Pages."""
import json, urllib.request, urllib.parse, time, re, sys
from datetime import datetime
from pathlib import Path

OPINET_KEY = sys.argv[1] if len(sys.argv) > 1 else "F260422158"
BASE = Path(__file__).parent

FUEL_PRODUCTS = {
    "휘발유": "B027",
    "경유": "D047",
    "고급휘발유": "B034",
    "LPG": "K015",
}
PRODUCT_TO_FUEL = {v: k for k, v in FUEL_PRODUCTS.items()}


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


def fmt_dt(td, tm):
    td = str(td or "").strip()
    tm = str(tm or "").strip().zfill(6)
    if not (td and tm):
        return "", ""
    try:
        dt = datetime.strptime(td + tm, "%Y%m%d%H%M%S")
        return dt.strftime("%y.%m.%d %H:%M"), dt.isoformat()
    except Exception:
        return "", ""


def default_fuel_for_row(row):
    product_code = row.get("opinet_product_code") or "B027"
    if row.get("fuel_type") in FUEL_PRODUCTS:
        return row["fuel_type"]
    return PRODUCT_TO_FUEL.get(product_code, "휘발유")


# Load existing station data
rows = json.loads((BASE / "station_data.json").read_text(encoding="utf-8"))
uni_ids = [r["opinet_uni_id"] for r in rows if r.get("opinet_uni_id")]
print(f"Refreshing prices for {len(uni_ids)} stations...")

for r in rows:
    uid = r.get("opinet_uni_id")
    primary_fuel = default_fuel_for_row(r)
    r["fuel_type"] = primary_fuel
    r["opinet_product_code"] = FUEL_PRODUCTS.get(primary_fuel, r.get("opinet_product_code") or "")
    old_fuel_prices = r.get("fuel_prices") if isinstance(r.get("fuel_prices"), dict) else {}

    if not uid:
        r.setdefault("gasoline_price_today", "")
        r.setdefault("price_num", None)
        r.setdefault("trade_dt", "")
        r.setdefault("trade_tm", "")
        r.setdefault("updated_at_fmt", r.get("updated_at_fmt", ""))
        r.setdefault("_updated_at_dt", r.get("_updated_at_dt", ""))
        r["fuel_prices"] = old_fuel_prices
        continue

    detail = opinet("detailById.do", {"id": uid})
    fuel_prices = dict(old_fuel_prices)
    if detail and "RESULT" in detail:
        oil_rows = detail["RESULT"].get("OIL", [])
        oil0 = oil_rows[0] if oil_rows else None
        if oil0:
            if oil0.get("OS_NM"):
                r.setdefault("opinet_os_nm", oil0.get("OS_NM"))
            if oil0.get("NEW_ADR") or oil0.get("VAN_ADR"):
                r.setdefault("opinet_new_adr", oil0.get("NEW_ADR") or oil0.get("VAN_ADR"))
            for p in oil0.get("OIL_PRICE", []) or []:
                fuel = PRODUCT_TO_FUEL.get(p.get("PRODCD"))
                if not fuel or not p.get("PRICE"):
                    continue
                price = int(p["PRICE"])
                updated_at_fmt, updated_at_dt = fmt_dt(p.get("TRADE_DT"), p.get("TRADE_TM"))
                fuel_prices[fuel] = {
                    "product_code": p.get("PRODCD"),
                    "price_text": f"{price}원/L",
                    "price_num": price,
                    "trade_dt": p.get("TRADE_DT", ""),
                    "trade_tm": p.get("TRADE_TM", ""),
                    "updated_at_fmt": updated_at_fmt,
                    "_updated_at_dt": updated_at_dt,
                }
    r["fuel_prices"] = fuel_prices

    primary = fuel_prices.get(primary_fuel) or fuel_prices.get("휘발유") or next(iter(fuel_prices.values()), None)
    if primary:
        r["gasoline_price_today"] = primary.get("price_text", "")
        r["price_num"] = primary.get("price_num")
        r["trade_dt"] = primary.get("trade_dt", "")
        r["trade_tm"] = primary.get("trade_tm", "")
        r["updated_at_fmt"] = primary.get("updated_at_fmt", "")
        r["_updated_at_dt"] = primary.get("_updated_at_dt", "")
    else:
        r.setdefault("gasoline_price_today", "")
        r.setdefault("price_num", None)
        r.setdefault("trade_dt", "")
        r.setdefault("trade_tm", "")
        r.setdefault("updated_at_fmt", "")
        r.setdefault("_updated_at_dt", "")
    time.sleep(0.15)

# Save updated data
(BASE / "station_data.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

# Rebuild HTML by replacing embedded rows array in template
html_rows = json.dumps(rows, ensure_ascii=False)
tmpl = (BASE / "template.html").read_text(encoding="utf-8")
html = re.sub(r"const rows=\[.*?\];", f"const rows={html_rows};", tmpl, count=1, flags=re.S)
(BASE / "index.html").write_text(html, encoding="utf-8")
print("index.html rebuilt successfully")
