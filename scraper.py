import sys
import time
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
from bs4 import BeautifulSoup

def get_starz_url_for_today():
    # Obté la data actual en format YYYY/MM/DD (ex: 2026/09/07)
    today = datetime.datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    return f"https://www.starz.com/us/en/schedule/STZ1/{year}/{month}/{day}", today

def fetch_starz_schedule():
    url, today_dt = get_starz_url_for_today()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        programs = []
        # Extracció dels blocs de programació de la graella de STARZ
        schedule_blocks = soup.select(".schedule-item, .program-card, [class*='ScheduleItem']")
        
        for item in schedule_blocks:
            time_elem = item.select_one(".time, [class*='time']")
            title_elem = item.select_one(".title, h3, [class*='title']")
            
            if title_elem:
                title = title_elem.get_text(strip=True)
                start_time = time_elem.get_text(strip=True) if time_elem else "00:00"
                programs.append({
                    "title": title,
                    "time": start_time
                })
        
        return programs, today_dt
    except Exception as e:
        print(f"Error en obtenir la graella de STARZ ({url}): {e}", file=sys.stderr)
        return [], today_dt

def generate_xmltv(programs, today_dt):
    date_str = today_dt.strftime("%Y%m%d")
    
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Scraper"})
    
    # Canal STARZ
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"
    
    if not programs:
        # Programa per defecte si falla l'scraping
        prog = ET.SubElement(tv, "programme", {
            "start": f"{date_str}000000 +0000",
            "stop": f"{date_str}235959 +0000",
            "channel": "starz-stz1"
        })
        title = ET.SubElement(prog, "title", lang="en")
        title.text = "STARZ Programming"
    else:
        for idx, prog_data in enumerate(programs):
            # Càlcul bàsic d'hores
            start_time_clean = prog_data["time"].replace(":", "").zfill(4) + "00"
            stop_time_clean = "235959" if idx == len(programs) - 1 else programs[idx+1]["time"].replace(":", "").zfill(4) + "00"
            
            prog = ET.SubElement(tv, "programme", {
                "start": f"{date_str}{start_time_clean} -0400",
                "stop": f"{date_str}{stop_time_clean} -0400",
                "channel": "starz-stz1"
            })
            title = ET.SubElement(prog, "title", lang="en")
            title.text = prog_data["title"]

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

def main():
    programs, today_dt = fetch_starz_schedule()
    xml_content = generate_xmltv(programs, today_dt)
    
    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(xml_content)

if __name__ == "__main__":
    main()
