import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import os
import pytz
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

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


def PAS_1_descarregar_html_complet(url):
    """Pas 1: Obre la web amb un navegador real, espera que carregui i ho guarda a 'starz_page.html'."""
    print(f"PAS 1: Descarregant la pàgina web des de {url}...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(5000)  # Espera 5 segons extra per assegurar-nos que tot el JS s'ha executat
            
            # Fer un desplaçament (scroll) per forçar la càrrega de tots els elements de la graella
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

            html_content = page.content()
            
            with open("starz_page.html", "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print("PAS 1 completat: S'ha descarregat i guardat 'starz_page.html' correctament.")
        except Exception as e:
            print(f"Error en descarregar la pàgina: {e}", file=sys.stderr)
        finally:
            browser.close()


def PAS_2_extraure_epg_des_de_html(now_ny):
    """Pas 2: Llegeix el fitxer local 'starz_page.html' i extreu la programació."""
    print("PAS 2: Processant el fitxer 'starz_page.html' local...")
    
    if not os.path.exists("starz_page.html"):
        print("Error: No es troba el fitxer starz_page.html", file=sys.stderr)
        return []

    with open("starz_page.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")
    programs = []

    # Cerquem tots els blocs de programa a l'HTML descarregat
    cards = soup.find_all(re.compile(r'div|section|article'))

    for card in cards:
        text = card.get_text(separator="\n").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        
        time_range = None
        title = None
        desc = ""
        rating = ""

        # Busquem la línia que conté l'interval horari (ex: "11:22 AM - 1:21 PM")
        for idx, line in enumerate(lines):
            match = re.search(r'\b\d{1,2}:\d{2}\s*(?:AM|PM)?\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM)?(?:\s*(?:EST|EDT))?\b', line, re.IGNORECASE)
            if match:
                time_range = match.group(0)
                
                # Normalment el títol està just abans o després de la línia de l'hora
                if idx > 0 and lines[idx-1] not in ["PLAY", "MORE INFO", "CC"]:
                    title = lines[idx-1]
                elif idx + 1 < len(lines):
                    title = lines[idx+1]
                break

        if time_range and title:
            # Ignorem títols buits o genèrics
            if title in ["PLAY", "MORE INFO", "CC", "STARZ"] or len(title) < 2:
                continue

            for l in lines:
                if l in ["TV-MA", "PG-13", "PG", "R", "G", "TV-14"]:
                    rating = l
                elif len(l) > 35 and "STARZ" not in l and not l.startswith("http"):
                    desc = l

            # Assegurem no afegir duplicats
            if not any(p["title"] == title and p["time_range"] == time_range for p in programs):
                programs.append({
                    "title": title,
                    "time_range": time_range,
                    "desc": desc,
                    "rating": rating
                })

    print(f"PAS 2 completat: S'han trobat {len(programs)} programes a l'HTML.")
    return programs


def main():
    now_ny = datetime.datetime.now(TZ_NY)
    date_path = now_ny.strftime("%Y/%m/%d")
    url = f"https://www.starz.com/us/en/schedule/STZ1/{date_path}"

    # Execució dels dos passos
    PAS_1_descarregar_html_complet(url)
    programs = PAS_2_extraure_epg_des_de_html(now_ny)

    # Generació del fitxer XMLTV
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Dos-Passos"})
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"

    count = 0
    for item in programs:
        try:
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
                val.text = item["rating"]
                
            count += 1
        except Exception as e:
            print(f"Error convertint el programa {item.get('title')}: {e}")

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    xml_content = reparsed.toprettyxml(indent="  ")

    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(f"S'ha generat l'EPG final amb {count} programes a epg.xml.")

if __name__ == "__main__":
    main()
