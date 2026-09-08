import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import os
import json
import subprocess
import pytz
from bs4 import BeautifulSoup

# Zones horàries: Nova York (EDT/UTC-4) i Catalunya (CEST/UTC+2)
TZ_NY = pytz.timezone("America/New_York")
TZ_CAT = pytz.timezone("Europe/Madrid")

def parse_iso_to_cat(iso_str):
    """Converteix cadenes ISO/UTC a l'horari de Catalunya (%Y%m%d%H%M%S +0200)."""
    try:
        if not iso_str:
            return None
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_cat = dt.astimezone(TZ_CAT)
        return dt_cat.strftime("%Y%m%d%H%M%S %z")
    except Exception:
        return None

def PAS_1_descarregar_html(url):
    print(f"Descarregant pàgina des de {url}...")
    cmd = [
        "curl", "-s", "-L",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "-H", "Accept-Language: en-US,en;q=0.9",
        url,
        "-o", "starz_page.html"
    ]
    try:
        subprocess.run(cmd, check=True)
        print("Pàgina 'starz_page.html' descarregada amb èxit.")
    except Exception as e:
        print(f"Error en descarregar amb curl: {e}", file=sys.stderr)

def PAS_2_extraure_next_data():
    if not os.path.exists("starz_page.html"):
        print("Error: No es troba el fitxer starz_page.html", file=sys.stderr)
        return []

    with open("starz_page.html", "r", encoding="utf-8", errors="ignore") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")
    next_data_script = soup.find("script", id="__NEXT_DATA__")

    if not next_data_script or not next_data_script.string:
        print("Error: No s'ha trobat el tag __NEXT_DATA__ a l'HTML.", file=sys.stderr)
        return []

    print("S'ha trobat el bloc __NEXT_DATA__. Parsejant el JSON complet...")

    try:
        data = json.loads(next_data_script.string)
    except Exception as e:
        print(f"Error parsejant el JSON de __NEXT_DATA__: {e}", file=sys.stderr)
        return []

    programs = []

    # Funció per recórrer recursivament l'objecte JSON de Next.js
    def extract_schedules(obj):
        if isinstance(obj, dict):
            # Comprovar si l'element té estructura de programa amb títol i horari
            title = obj.get("title") or obj.get("titleName") or obj.get("name")
            start_iso = obj.get("startTime") or obj.get("airStart") or obj.get("start")
            end_iso = obj.get("endTime") or obj.get("airEnd") or obj.get("end")
            desc = obj.get("description") or obj.get("synopsis") or obj.get("logLine", "")
            rating = obj.get("rating") or obj.get("contentRating", "")

            # Si trobem un bloc vàlid amb títol i data d'inici ISO
            if title and start_iso and isinstance(start_iso, str) and ("T" in start_iso or "Z" in start_iso):
                if not any(p["title"] == title and p["start_iso"] == start_iso for p in programs):
                    programs.append({
                        "title": title,
                        "start_iso": start_iso,
                        "end_iso": end_iso,
                        "desc": desc,
                        "rating": rating
                    })

            for value in obj.values():
                extract_schedules(value)

        elif isinstance(obj, list):
            for item in obj:
                extract_schedules(item)

    extract_schedules(data)
    print(f"S'han extret {len(programs)} programes del JSON de Next.js.")
    return programs

def main():
    now_ny = datetime.datetime.now(TZ_NY)
    date_path = now_ny.strftime("%Y/%m/%d")
    url = f"https://www.starz.com/us/en/schedule/STZ1/{date_path}"

    PAS_1_descarregar_html(url)
    programs = PAS_2_extraure_next_data()

    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-NextJS-Full"})
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"

    count = 0
    for item in programs:
        start_cat = parse_iso_to_cat(item.get("start_iso"))
        stop_cat = parse_iso_to_cat(item.get("end_iso")) or start_cat

        if not start_cat:
            continue

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

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    xml_content = reparsed.toprettyxml(indent="  ")

    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(f"Proces finalitzat. S'han escrit {count} programes a epg.xml.")

if __name__ == "__main__":
    main()
