import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import os
import subprocess
import pytz
from bs4 import BeautifulSoup

# Zones horàries
TZ_NY = pytz.timezone("America/New_York")
TZ_CAT = pytz.timezone("Europe/Madrid")

def parse_time_string(time_str):
    time_str = time_str.strip().upper()
    return datetime.datetime.strptime(time_str, "%I:%M %p").time()

def convert_range_ny_to_cat(time_range_str, base_date_ny):
    clean_str = re.sub(r'\b(EST|EDT)\b', '', time_range_str, flags=re.IGNORECASE).strip()
    parts = clean_str.split('-')
    
    if len(parts) != 2:
        start_t = parse_time_string(clean_str)
        dt_start_ny = TZ_NY.localize(datetime.datetime.combine(base_date_ny.date(), start_t))
        dt_start_cat = dt_start_ny.astimezone(TZ_CAT)
        dt_stop_cat = dt_start_cat + datetime.timedelta(hours=2)
        return dt_start_cat.strftime("%Y%m%d%H%M%S %z"), dt_stop_cat.strftime("%Y%m%d%H%M%S %z")

    start_str, stop_str = parts[0].strip(), parts[1].strip()
    
    if not re.search(r'(AM|PM)', start_str, re.IGNORECASE):
        period = "PM" if "PM" in stop_str.upper() else "AM"
        start_str = f"{start_str} {period}"

    start_t = parse_time_string(start_str)
    stop_t = parse_time_string(stop_str)

    dt_start_ny = TZ_NY.localize(datetime.datetime.combine(base_date_ny.date(), start_t))
    
    stop_date = base_date_ny.date()
    if stop_t < start_t:
        stop_date += datetime.timedelta(days=1)
        
    dt_stop_ny = TZ_NY.localize(datetime.datetime.combine(stop_date, stop_t))

    dt_start_cat = dt_start_ny.astimezone(TZ_CAT)
    dt_stop_cat = dt_stop_ny.astimezone(TZ_CAT)

    return dt_start_cat.strftime("%Y%m%d%H%M%S %z"), dt_stop_cat.strftime("%Y%m%d%H%M%S %z")

def PAS_1_descarregar_amb_curl(url):
    """Pas 1: Descarrega la web de STARZ bypassejant bot-detectors mitjançant curl natiu de Linux."""
    print(f"PAS 1: Descarregant la pàgina web des de {url} utilitzant curl...")
    
    cmd = [
        "curl", "-s", "-L",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-H", "Sec-Fetch-Dest: document",
        "-H", "Sec-Fetch-Mode: navigate",
        "-H", "Sec-Fetch-Site: none",
        "-H", "Sec-Fetch-User: ?1",
        "-H", "Upgrade-Insecure-Requests: 1",
        url,
        "-o", "starz_page.html"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("PAS 1 completat: 'starz_page.html' generat correctament.")
    except Exception as e:
        print(f"Error en descarregar la pàgina amb curl: {e}", file=sys.stderr)

def PAS_2_extraure_epg(now_ny):
    """Pas 2: Analitza l'HTML o JSON contingut dins del fitxer descarregat."""
    print("PAS 2: Analitzant el contingut de 'starz_page.html'...")
    
    if not os.path.exists("starz_page.html"):
        print("Error: No existeix el fitxer starz_page.html", file=sys.stderr)
        return []

    with open("starz_page.html", "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    programs = []

    # Cerquem si hi ha estructures de dades en text/json
    json_blocks = re.findall(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', content, re.DOTALL)
    for block in json_blocks:
        if "schedule" in block or "title" in block:
            try:
                import json
                data = json.loads(block)
                # Extreure recursivament del JSON si existeix
                def find_titles(obj):
                    if isinstance(obj, dict):
                        if ("title" in obj or "titleName" in obj) and ("startTime" in obj or "airStart" in obj):
                            t = obj.get("title") or obj.get("titleName")
                            s = obj.get("startTime") or obj.get("airStart")
                            e = obj.get("endTime") or obj.get("airEnd")
                            d = obj.get("description") or obj.get("synopsis", "")
                            r = obj.get("rating", "")
                            if t and s:
                                programs.append({"title": t, "start_iso": s, "end_iso": e, "desc": d, "rating": r})
                        for v in obj.values():
                            find_titles(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            find_titles(item)
                find_titles(data)
            except Exception:
                pass

    # Si no troba blocs JSON interns, parseja el text HTML estructurat
    if not programs:
        soup = BeautifulSoup(content, "html.parser")
        text_blocks = soup.get_text(separator="\n").split("\n")
        lines = [l.strip() for l in text_blocks if l.strip()]

        for idx, line in enumerate(lines):
            # Cercar línies de temps (ex: "11:22 AM - 1:21 PM" o "11:22 AM - 1:21 PM EST")
            match = re.search(r'\b\d{1,2}:\d{2}\s*(?:AM|PM)?\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM)?(?:\s*(?:EST|EDT))?\b', line, re.IGNORECASE)
            if match:
                time_range = match.group(0)
                title = None
                
                # Agafar el títol adjacent que no sigui un botó de navegació
                if idx > 0 and lines[idx-1] not in ["PLAY", "MORE INFO", "CC", "STARZ"]:
                    title = lines[idx-1]
                elif idx + 1 < len(lines):
                    title = lines[idx+1]

                if title and len(title) > 1 and title not in ["PLAY", "MORE INFO", "CC"]:
                    if not any(p.get("title") == title and p.get("time_range") == time_range for p in programs):
                        programs.append({
                            "title": title,
                            "time_range": time_range,
                            "desc": "",
                            "rating": ""
                        })

    print(f"PAS 2 completat: S'han trobat {len(programs)} programes.")
    return programs

def main():
    now_ny = datetime.datetime.now(TZ_NY)
    date_path = now_ny.strftime("%Y/%m/%d")
    url = f"https://www.starz.com/us/en/schedule/STZ1/{date_path}"

    PAS_1_descarregar_amb_curl(url)
    programs = PAS_2_extraure_epg(now_ny)

    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Curl"})
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"

    count = 0
    for item in programs:
        try:
            if "start_iso" in item and item["start_iso"]:
                # Si ve d'un format ISO
                dt_start = datetime.datetime.fromisoformat(item["start_iso"].replace("Z", "+00:00")).astimezone(TZ_CAT)
                start_cat = dt_start.strftime("%Y%m%d%H%M%S %z")
                stop_cat = start_cat
                if item.get("end_iso"):
                    dt_stop = datetime.datetime.fromisoformat(item["end_iso"].replace("Z", "+00:00")).astimezone(TZ_CAT)
                    stop_cat = dt_stop.strftime("%Y%m%d%H%M%S %z")
            else:
                # Si ve del format de text d'interval
                start_cat, stop_cat = convert_range_ny_to_cat(item["time_range"], now_ny)

            prog = ET.SubElement(tv, "programme", {
                "start": start_cat,
                "stop": stop_cat,
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
                val.text = str(item["rating"])
                
            count += 1
        except Exception as e:
            print(f"Error en afegir programa {item.get('title')}: {e}")

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    xml_content = reparsed.toprettyxml(indent="  ")

    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(f"Procés finalitzat. {count} programes escrits a epg.xml.")

if __name__ == "__main__":
    main()
