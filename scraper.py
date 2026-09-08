import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import pytz

TZ_NY = pytz.timezone("America/New_York")
TZ_CAT = pytz.timezone("Europe/Madrid")

def get_starz_schedule():
    now_ny = datetime.datetime.now(TZ_NY)
    date_str = now_ny.strftime("%Y-%m-%d")
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.starz.com",
        "Referer": "https://www.starz.com/"
    })

    programs = []

    try:
        # Pas 1: Obtenir token d'autenticació anònim
        auth_url = "https://api.starz.com/v2/authentication/anonymous"
        auth_payload = {"deviceType": "Web", "operatingSystem": "Windows"}
        auth_res = session.post(auth_url, json=auth_payload, timeout=15)
        
        headers = {}
        if auth_res.status_code == 200:
            auth_data = auth_res.json()
            token = auth_data.get("token") or auth_data.get("accessToken")
            if token:
                headers["Authorization"] = f"Bearer {token}"
                print("Token d'autenticació STARZ obtingut correctament.")

        # Pas 2: Cridar l'API de la graella de programació per al canal STZ1
        schedule_url = f"https://api.starz.com/v2/schedules/us/STZ1?startDate={date_str}&days=1"
        res = session.get(schedule_url, headers=headers, timeout=15)
        
        if res.status_code != 200:
            # Fallback si l'endpoint de data difereix
            schedule_url = f"https://api.starz.com/v2/schedules/us/STZ1/{date_str}"
            res = session.get(schedule_url, headers=headers, timeout=15)

        if res.status_code == 200:
            data = res.json()
            # La resposta pot ser una llista o un objecte amb la clau 'schedule' o 'titles'
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("schedule") or data.get("titles") or data.get("blocks", [])

            for item in items:
                title = item.get("title") or item.get("titleName") or item.get("name")
                start_iso = item.get("startTime") or item.get("airStart") or item.get("start")
                end_iso = item.get("endTime") or item.get("airEnd") or item.get("end")
                desc = item.get("description") or item.get("synopsis") or item.get("logLine", "")
                rating = item.get("rating") or item.get("contentRating", "")

                if title and start_iso:
                    programs.append({
                        "title": title,
                        "start_iso": start_iso,
                        "end_iso": end_iso,
                        "desc": desc,
                        "rating": rating
                    })
        else:
            print(f"Error en la petició EPG. Codi de resposta: {res.status_code}", file=sys.stderr)

    except Exception as e:
        print(f"Error de connexió amb l'API de STARZ: {e}", file=sys.stderr)

    return programs, now_ny

def parse_iso_to_cat(iso_str):
    """Converteix la data ISO de l'API a l'hora oficial de Catalunya en format XMLTV (+0200)."""
    try:
        if not iso_str:
            return None
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_cat = dt.astimezone(TZ_CAT)
        return dt_cat.strftime("%Y%m%d%H%M%S %z")
    except Exception:
        return None

def main():
    programs, now_ny = get_starz_schedule()
    
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Catalunya"})
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
        
    print(f"S'han afegit {count} programes a l'arxiu epg.xml.")

if __name__ == "__main__":
    main()
