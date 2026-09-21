#!/usr/bin/env python3
"""Fetch current weather values from every station web page listed in stationIP.csv
and write them to station_weather.json (read by station_ip_check.html).

Usage: python fetch_station_weather.py [stationIP.csv] [station_weather.json]
Standard library only.
"""
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

CSV_FILE = sys.argv[1] if len(sys.argv) > 1 else "stationIP.csv"
OUT_FILE = sys.argv[2] if len(sys.argv) > 2 else "station_weather.json"
TIMEOUT = 12          # seconds to wait for each station
WORKERS = 20          # stations fetched at the same time
DEFAULT_PORT = "8000"
IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def text_from_html(html):
    html = re.sub(r"<(script|style)[\s\S]*?</\1>", "", html, flags=re.I)
    html = re.sub(r"<br\s*/?>|</(p|div|tr|li|h[1-6]|pre|table)>", "\n", html, flags=re.I)
    html = re.sub(r"</t[dh]>", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    return html.replace("&nbsp;", " ").replace("&deg;", "°").replace("&amp;", "&").replace("\r", "")


def num(pattern, text):
    m = re.search(pattern, text, flags=re.I)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_weather(html):
    text = text_from_html(html)
    m = re.search(r"Weather Station:\s*(.+)", text, flags=re.I)
    d = {
        "station": m.group(1).strip() if m else "",
        "timeText": "", "tz": "", "obsMin": None, "ageMin": None,
        "dir": num(r"Wind Direction:\s*(-?[\d.]+)", text),
        "speed": num(r"Wind Speed:\s*(-?[\d.]+)", text),
        "gust": num(r"Wind Gust[^:\n]*:\s*(-?[\d.]+)", text),
        "gustDir": num(r"Wind Direction of Gust[^:\n]*:\s*(-?[\d.]+)", text),
        "temp": num(r"Temperature:\s*(-?[\d.]+)", text),
        "rh": num(r"Relative Humidity:\s*(-?[\d.]+)", text),
    }
    if all(d[k] is None for k in ("dir", "speed", "gust", "gustDir", "temp", "rh")):
        return None
    t = re.search(r"Time:\s*(\d{1,2}):(\d{2})\s*([A-Za-z]{2,4})?", text, flags=re.I)
    if t:
        d["timeText"] = "%s:%s" % (t.group(1), t.group(2))
        d["tz"] = (t.group(3) or "").upper()
        d["obsMin"] = int(t.group(1)) * 60 + int(t.group(2))
        offset = 360 if d["tz"] == "MDT" else 420          # minutes behind UTC
        now = datetime.now(timezone.utc)
        d["ageMin"] = (now.hour * 60 + now.minute - offset - d["obsMin"]) % 1440
    return d


def web_port(web_url):
    m = re.search(r"\d+\.\d+\.\d+\.\d+:(\d+)", web_url or "")
    return m.group(1) if m and len(m.group(1)) >= 4 else DEFAULT_PORT


def load_stations():
    with open(CSV_FILE, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = [h.strip() for h in rows[0]]

    def col(name, prefix=False):
        for i, h in enumerate(header):
            if (h.startswith(name) if prefix else h == name):
                return i
        return -1

    ix = {"id": col("Stn. ID"), "name": col("Station Name"), "ip": col("IP Address"),
          "web": col("Web Access", True)}
    out = []
    for r in rows[1:]:
        def get(k):
            i = ix[k]
            return r[i].strip() if 0 <= i < len(r) else ""
        if not get("id") or not IP_RE.match(get("ip")):
            continue
        out.append({"id": get("id"), "name": get("name"), "ip": get("ip"),
                    "port": web_port(get("web"))})
    return out


def fetch(st):
    url = "http://%s:%s/" % (st["ip"], st["port"])
    rec = {"id": st["id"], "name": st["name"], "ip": st["ip"], "port": st["port"],
           "ok": False, "error": "", "ms": None, "data": None, "hourly": ""}
    t0 = monotonic()
    try:
        req = Request(url, headers={"User-Agent": "chnwx-station-feed/1.0"})
        try:
            resp = urlopen(req, timeout=TIMEOUT)
        except HTTPError as e:          # the station answered, just not with 200
            resp = e
        body = resp.read(300000).decode("utf-8", errors="replace")
        rec["ok"] = True
        rec["ms"] = int((monotonic() - t0) * 1000)
        rec["data"] = parse_weather(body)
        m = re.search(r"href\s*=\s*[\"']([^\"']*TableDisplay[^\"']*)[\"']", body, flags=re.I)
        if m:
            rec["hourly"] = urljoin(url, m.group(1))
        if rec["data"] is None:
            rec["error"] = "Answered, but no weather values found"
    except Exception as e:              # timeout, refused, reset, unreachable...
        rec["error"] = (str(getattr(e, "reason", "") or e) or e.__class__.__name__)[:120]
    return rec


def main():
    stations = load_stations()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(fetch, stations))
    feed = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stations": {r["id"]: r for r in results},
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=1, ensure_ascii=False)
    answered = sum(1 for r in results if r["ok"])
    with_data = sum(1 for r in results if r["data"])
    print("%d stations: %d answered, %d with weather values, %d no answer"
          % (len(results), answered, with_data, len(results) - answered))


if __name__ == "__main__":
    main()
