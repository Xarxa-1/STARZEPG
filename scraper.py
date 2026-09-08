import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import pytz
from playwright.sync_api import sync_playwright

# Zones horàries: Nova York (EDT / UTC-4) i Catalunya (CEST / UTC+2)
TZ_NY = pytz.timezone("America/New_York")
TZ_CAT = pytz.timezone("Europe/Madrid")

def parse_time_string(time_str):
    time_str = time_str.strip().upper()
    return datetime.datetime.strptime(time_str, "%I:%M %p").time()

def convert_range_ny_to_cat(time_range_str, base_date_ny):
    """
    Converteix els intervals d'hora de Nova York (EDT) a Catalunya (CEST),
    sumant les 6 hores de diferència i gestionant salts de dia.
    """
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

def scrape_starz_live():
    now_ny = datetime.datetime.now(TZ_NY)
    year = now_ny.strftime("%Y")
    month = now_ny.strftime("%m")
    day = now_ny.strftime("%d")
    url = f"https://www.starz.com/us/en/schedule/STZ1/{year}/{month}/{day}"

    programs = []

    with sync_playwright() as p:
        # Arrencar un navegador virtual (headless)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            print(f"Carregant la graella real des de: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Esperar a que el contingut de la programació estigui present
            page.wait_for_selector("text=MORE INFO", timeout=15000)
            
            # Obtenir tots els blocs de programa de la pàgina
            elements = page.query_selector_all("section, article, div[class*='Schedule'], div[class*='schedule']")
            
            for elem in elements:
                text = elem.inner_text()
                if "MORE INFO" in text or "PLAY" in text:
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    title = ""
                    time_range = ""
                    desc = ""
                    rating = ""

                    for idx, line in enumerate(lines):
                        # Buscar línies d'interval horari com '11:22 AM - 1:21 PM EST'
                        if re.search(r'\d{1,2}:\d{2}.*?-.*?\d{1,2}:\d{2}', line):
                            time_range = line
                            if idx > 0 and not title:
                                title = lines[idx-1]
                        
                        if line in ["TV-MA", "PG-13", "PG", "R", "G", "TV-14"]:
                            rating = line
                            
                        if len(line) > 30 and not line.startswith("http") and "STARZ" not in line:
                            desc = line

                    if title and time_range and title not in [p["title"] for p in programs]:
                        programs.append({
                            "title": title,
                            "time_range": time_range,
                            "desc": desc,
                            "rating": rating
                        })

        except Exception as e:
            print(f"Error durant l'scraping dinàmic: {e}", file=sys.stderr)
        finally:
            browser.close()

    return programs, now_ny

def main():
    programs, now_ny = scrape_starz_live()
    
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Playwright-Realtime"})
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"

    if not programs:
        print("Atenció: No s'han pogut extreure programes en directe.")
        return

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
        except Exception as e:
            print(f"Error processant el programa {item.get('title')}: {e}")

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    xml_content = reparsed.toprettyxml(indent="  ")

    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(xml_content)

if __name__ == "__main__":
    main()
