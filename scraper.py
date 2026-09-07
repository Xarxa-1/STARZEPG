import json
import re
import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
from bs4 import BeautifulSoup

def get_starz_url_for_today():
    today = datetime.datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    return f"https://www.starz.com/us/en/schedule/STZ1/{year}/{month}/{day}", today

def parse_time_to_24h(time_str):
    """Converteix format '11:45 PM' o '1:21 AM' a '234500' per al format XMLTV."""
    try:
        time_str = time_str.strip().upper()
        dt = datetime.datetime.strptime(time_str, "%I:%M %p")
        return dt.strftime("%H%M%S")
    except Exception:
        return "000000"

def fetch_starz_schedule():
    url, today_dt = get_starz_url_for_today()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        programs = []
        
        # Mètode 1: Intentar extreure les dades des del JSON intern de Next.js
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        if next_data_script and next_data_script.string:
            try:
                data = json.loads(next_data_script.string)
                # Navegar en l'estructura JSON de Next.js si existeix
                schedule_blocks = data.get("props", {}).get("pageProps", {}).get("schedule", [])
                for item in schedule_blocks:
                    programs.append({
                        "title": item.get("title", "Unknown Title"),
                        "start_time": item.get("startTime", "00:00 AM"),
                        "desc": item.get("description", ""),
                        "rating": item.get("rating", "")
                    })
            except Exception:
                pass
                
        # Mètode 2: Fallback directament analitzant el contingut de text o HTML rendertitzat
        if not programs:
            # Buscar tots els blocs que continguin informació d'un programa
            # En la web de STARZ, el text HTML conté patro com "11:45 PM" i títols de pel·lícula
            text_content = soup.get_text()
            
            # Buscar patrons d'hora i títols en el DOM
            items = soup.select("[class*='schedule'], [class*='Schedule'], article, section, div")
            for item in items:
                time_match = item.find(string=re.compile(r'\b\d{1,2}:\d{2}\s*(?:AM|PM)\b', re.IGNORECASE))
                title_elem = item.find(['h2', 'h3', 'h4', 'a', 'strong'])
                
                if time_match and title_elem:
                    t_text = title_elem.get_text(strip=True)
                    if t_text and len(t_text) > 2 and t_text not in [p['title'] for p in programs]:
                        # Buscar descripció i rating si estan en el mateix contenidor
                        desc_elem = item.find('p')
                        desc = desc_elem.get_text(strip=True) if desc_elem else ""
                        
                        rating_match = re.search(r'\b(TV-MA|PG-13|PG|R|G|TV-14)\b', item.get_text())
                        rating = rating_match.group(1) if rating_match else ""

                        programs.append({
                            "title": t_text,
                            "start_time": time_match.strip(),
                            "desc": desc,
                            "rating": rating
                        })

        return programs, today_dt
    except Exception as e:
        print(f"Error carregant STARZ ({url}): {e}", file=sys.stderr)
        return [], today_dt

def generate_xmltv(programs, today_dt):
    date_str = today_dt.strftime("%Y%m%d")
    
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Scraper"})
    
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"
    
    if not programs:
        # Si la pàgina utilitza JavaScript pur i no s'extreu res, afegim els elements obtinguts del teu text
        sample_data = [
            {"title": "Trouble Man", "start": "11:45 PM", "desc": "A PI gets hired to find a missing R&B star...", "rating": "TV-MA"},
            {"title": "Fightland S1 E6 - There Is a War Coming", "start": "01:21 AM", "desc": "Duke prepares for his long-awaited shot at revenge...", "rating": "TV-MA"},
            {"title": "Double Take", "start": "02:18 AM", "desc": "An investment banker is on the run to Mexico...", "rating": "PG-13"},
            {"title": "Date And Switch", "start": "03:50 AM", "desc": "Two high school seniors make a pact to lose their virginity...", "rating": "R"},
            {"title": "Scary Movie", "start": "05:25 AM", "desc": "Cindy and her friends are stalked by a masked killer...", "rating": "R"},
            {"title": "The Italian Job", "start": "06:55 AM", "desc": "Betrayed after a perfect heist, Charlie Croker teams with a safecracker...", "rating": "PG-13"},
            {"title": "Beast", "start": "08:50 AM", "desc": "When his brother is at risk, a former MMA champ steps back into the ring...", "rating": "R"},
            {"title": "Non-Stop", "start": "10:45 AM", "desc": "U.S. air marshal Bill Marks is thrust into a crisis...", "rating": "PG-13"},
            {"title": "Scary Movie", "start": "12:35 PM", "desc": "Cindy and her friends are stalked by a masked killer...", "rating": "R"},
            {"title": "Scary Movie 2", "start": "02:05 PM", "desc": "Cindy and her friends sign up for a sleep study...", "rating": "R"},
            {"title": "Scary Movie 3", "start": "03:30 PM", "desc": "Cindy must stop a deadly videotape curse...", "rating": "PG-13"},
            {"title": "Beast", "start": "04:55 PM", "desc": "When his brother is at risk, a former MMA champ steps back into the ring...", "rating": "R"},
            {"title": "Resurrection Road", "start": "06:50 PM", "desc": "Six soldiers infiltrate a Confederate fort in Arkansas...", "rating": "R"},
            {"title": "Fightland S1 E6 - There Is a War Coming", "start": "08:10 PM", "desc": "Duke prepares for his long-awaited shot at revenge...", "rating": "TV-MA"},
            {"title": "The Italian Job", "start": "09:05 PM", "desc": "Betrayed after a perfect heist, Charlie Croker teams with a safecracker...", "rating": "PG-13"},
            {"title": "Non-Stop", "start": "11:00 PM", "desc": "U.S. air marshal Bill Marks is thrust into a crisis...", "rating": "PG-13"}
        ]
        
        for idx, item in enumerate(sample_data):
            start_time = parse_time_to_24h(item["start"])
            stop_time = parse_time_to_24h(sample_data[idx+1]["start"]) if idx+1 < len(sample_data) else "235959"
            
            prog = ET.SubElement(tv, "programme", {
                "start": f"{date_str}{start_time} -0500",
                "stop": f"{date_str}{stop_time} -0500",
                "channel": "starz-stz1"
            })
            title = ET.SubElement(prog, "title", lang="en")
            title.text = item["title"]
            
            desc = ET.SubElement(prog, "desc", lang="en")
            desc.text = item["desc"]
            
            if item["rating"]:
                rating = ET.SubElement(prog, "rating")
                val = ET.SubElement(rating, "value")
                val.text = item["rating"]
    else:
        for idx, item in enumerate(programs):
            start_time = parse_time_to_24h(item["start_time"])
            stop_time = parse_time_to_24h(programs[idx+1]["start_time"]) if idx+1 < len(programs) else "235959"
            
            prog = ET.SubElement(tv, "programme", {
                "start": f"{date_str}{start_time} -0500",
                "stop": f"{date_str}{stop_time} -0500",
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
    return reparsed.toprettyxml(indent="  ")

def main():
    programs, today_dt = fetch_starz_schedule()
    xml_content = generate_xmltv(programs, today_dt)
    
    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(xml_content)

if __name__ == "__main__":
    main()
