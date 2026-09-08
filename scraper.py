import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import re
import json
import pytz

TZ_NY = pytz.timezone("America/New_York")
TZ_CAT = pytz.timezone("Europe/Madrid")

def parse_iso_or_utc(date_str):
    """Converteix cadenes de data ISO a l'hora exacta de Catalunya (+0200)."""
    try:
        if date_str.endswith("Z"):
            date_str = date_str.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(date_str)
        dt_cat = dt.astimezone(TZ_CAT)
        return dt_cat.strftime("%Y%m%d%H%M%S %z")
    except Exception:
        return None

def fetch_schedule_via_html_json():
    now_ny = datetime.datetime.now(TZ_NY)
    date_path = now_ny.strftime("%Y/%m/%d")
    url = f"https://www.starz.com/us/en/schedule/STZ1/{date_path}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }

    programs = []

    try:
        print(f"Obtenint la graella des de: {url}")
        res = requests.get(url, headers=headers, timeout=20)
        
        if res.status_code == 200:
            # Cercar dades JSON internes que STARZ insereix a la pàgina
            matches = re.findall(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text, re.DOTALL)
            
            if matches:
                data = json.loads(matches[0])
                # Processar l'arbre de dades del framework Next.js / React
                page_props = data.get("props", {}).get("pageProps", {})
                
                schedule_list = []
                if "schedule" in page_props:
                    schedule_list = page_props["schedule"]
                elif "initialData" in page_props:
                    schedule_list = page_props["initialData"].get("schedule", [])

                for item in schedule_list:
                    title = item.get("title") or item.get("titleName") or item.get("name")
                    start_str = item.get("startTime") or item.get("airStart")
                    end_str = item.get("endTime") or item.get("airEnd")
                    desc = item.get("description") or item.get("synopsis") or item.get("logLine", "")
                    rating = item.get("rating") or item.get("contentRating", "")

                    if title and start_str:
                        programs.append({
                            "title": title,
                            "start": start_str,
                            "end": end_str,
                            "desc": desc,
                            "rating": rating
                        })

    except Exception as e:
        print(f"Error processant l'HTML/JSON de STARZ: {e}", file=sys.stderr)

    return programs, now_ny

def main():
    programs, now_ny = fetch_schedule_via_html_json()
    
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Catalunya"})
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"

    if not programs:
        print("Atenció: No s'ha trobat l'estructura JSON esperada. Generant estructura base buida.")
        # Generem l'XML bàsic sense aturar el workflow amb error
        rough_string = ET.tostring(tv, encoding="utf-8")
        reparsed = minidom.parseString(rough_string)
        with open("epg.xml", "w", encoding="utf-8") as f:
            f.write(reparsed.toprettyxml(indent="  "))
        sys.exit(0)

    count = 0
    for item in programs:
        start_cat = parse_iso_or_utc(item["start"])
        stop_cat = parse_iso_or_utc(item["end"]) if item.get("end") else start_cat

        if not start_cat:
            continue

        prog = ET.SubElement(tv, "programme", {
            "start": start_cat,
            "stop": stop_cat if stop_cat else start_cat,
            "channel": "starz-stz1"
        })
        
        title = ET.SubElement(prog, "title", lang="en")
        title.text = item["title"]
        
        if item.get("desc"):
            desc = ET.SubElement(prog, "desc", lang="en")
            desc.text = item["desc"]
            
        if item.get("rating"):
            rating = ET.SubElement(prog, "rating")
            val = ET.SubElement(rating, "value")
            val.text = item["rating"]
        
        count += 1

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    xml_content = reparsed.toprettyxml(indent="  ")

    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(f"S'han processat i convertit {count} programes a l'horari de Catalunya amb èxit.")

if __name__ == "__main__":
    main()
