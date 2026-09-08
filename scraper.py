import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import pytz

TZ_NY = pytz.timezone("America/New_York")
TZ_CAT = pytz.timezone("Europe/Madrid")

def fetch_starz_api_schedule():
    now_ny = datetime.datetime.now(TZ_NY)
    date_str = now_ny.strftime("%Y-%m-%d")
    
    # Endpoint oficial de l'API de STARZ per a la llista de canals i la graella EPG
    api_url = f"https://api.starz.com/v2/schedules/us/STZ1/{date_str}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.starz.com",
        "Referer": "https://www.starz.com/"
    }
    
    programs = []
    
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            # Si l'API retorna l'estructura d'elements directa
            schedule_items = data.get("schedule", []) or data.get("titles", []) or data
            if isinstance(schedule_items, list):
                for item in schedule_items:
                    title = item.get("title") or item.get("titleName") or item.get("name")
                    start_iso = item.get("startTime") or item.get("airStart")
                    end_iso = item.get("endTime") or item.get("airEnd")
                    desc = item.get("description") or item.get("synopsis") or ""
                    rating = item.get("rating") or item.get("contentRating") or ""
                    
                    if title and start_iso:
                        programs.append({
                            "title": title,
                            "start_iso": start_iso,
                            "end_iso": end_iso,
                            "desc": desc,
                            "rating": rating
                        })
    except Exception as e:
        print(f"Error cridant l'API principal de STARZ: {e}", file=sys.stderr)

    # Si l'API directa té restricció de capçalera, utilitzem l'endpoint de fallback d'agregació
    if not programs:
        print("S'utilitza l'endpoint secundari d'extracció de contingut...")
        fallback_url = f"https://www.starz.com/api/v2/schedules/STZ1?date={date_str}"
        try:
            res = requests.get(fallback_url, headers=headers, timeout=15)
            if res.status_code == 200:
                items = res.json()
                for item in items:
                    programs.append({
                        "title": item.get("title", "Unknown"),
                        "start_iso": item.get("startTime"),
                        "end_iso": item.get("endTime"),
                        "desc": item.get("logLine", ""),
                        "rating": item.get("rating", "")
                    })
        except Exception as e:
            print(f"Error en l'endpoint de fallback: {e}", file=sys.stderr)

    return programs, now_ny

def iso_to_cat_xmltv(iso_str):
    """Converteix qualsevol data ISO/UTC o EDT directament a la zona horària de Catalunya."""
    try:
        # Neteja de la cadena ISO de la API
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_cat = dt.astimezone(TZ_CAT)
        return dt_cat.strftime("%Y%m%d%H%M%S %z")
    except Exception:
        return None

def main():
    programs, now_ny = fetch_starz_api_schedule()
    
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-API-Catalunya"})
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"

    if not programs:
        print("No s'ha pogut obtenir la graella de la API de STARZ.", file=sys.stderr)
        sys.exit(1)

    for item in programs:
        start_cat = iso_to_cat_xmltv(item["start_iso"]) if item.get("start_iso") else None
        stop_cat = iso_to_cat_xmltv(item["end_iso"]) if item.get("end_iso") else None
        
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

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    xml_content = reparsed.toprettyxml(indent="  ")

    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(f"EPG actualitzat amb èxit. S'han processat {len(programs)} programes.")

if __name__ == "__main__":
    main()
