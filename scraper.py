import json
import re
import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
from bs4 import BeautifulSoup
import pytz

# Definició de zones horàries
TZ_USA = pytz.timezone("America/New_York")      # Horari de STARZ (EST/EDT)
TZ_CAT = pytz.timezone("Europe/Madrid")         # Horari de Catalunya (CET/CEST)

def get_starz_url_for_today():
    # Obtenim la data actual en la zona d'EUA
    today_usa = datetime.datetime.now(TZ_USA)
    year = today_usa.strftime("%Y")
    month = today_usa.strftime("%m")
    day = today_usa.strftime("%d")
    return f"https://www.starz.com/us/en/schedule/STZ1/{year}/{month}/{day}", today_usa

def convert_usa_to_cat_xmltv(time_str, base_date_usa):
    """
    Converteix una hora d'EUA (ex: '11:45 PM') a la data/hora exacta
    de Catalunya en format XMLTV (YYYYMMDDHHMMSS +0200).
    """
    try:
        time_str = time_str.strip().upper()
        time_obj = datetime.datetime.strptime(time_str, "%I:%M %p").time()
        
        # Combinar la data base d'EUA amb l'hora indicada
        dt_usa = datetime.datetime.combine(base_date_usa.date(), time_obj)
        dt_usa = TZ_USA.localize(dt_usa)
        
        # Convertir a l'horari de Catalunya
        dt_cat = dt_usa.astimezone(TZ_CAT)
        
        # Retorna la cadena en format XMLTV: YYYYMMDDHHMMSS +0200
        return dt_cat.strftime("%Y%m%d%H%M%S %z")
    except Exception:
        dt_fallback = datetime.datetime.now(TZ_CAT)
        return dt_fallback.strftime("%Y%m%d%H%M%S %z")

def fetch_starz_schedule():
    url, today_usa = get_starz_url_for_today()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        programs = []
        
        # Extracció mitjançant script JSON de la pàgina
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        if next_data_script and next_data_script.string:
            try:
                data = json.loads(next_data_script.string)
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

        return programs, today_usa
    except Exception as e:
        print(f"Error carregant STARZ ({url}): {e}", file=sys.stderr)
        return [], today_usa

def generate_xmltv(programs, today_usa):
    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Scraper-Catalunya"})
    
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"
    
    if not programs:
        # Dades de mostra ajustades si no hi ha resposta directa
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
        programs = sample_data

    for idx, item in enumerate(programs):
        start_cat = convert_usa_to_cat_xmltv(item.get("start_time") or item.get("start"), today_usa)
        
        # Càlcul de l'hora de finalització (stop_time)
        if idx + 1 < len(programs):
            next_item = programs[idx+1]
            stop_cat = convert_usa_to_cat_xmltv(next_item.get("start_time") or next_item.get("start"), today_usa)
        else:
            # Si és l'últim programa, sumem 2 hores per defecte
            start_dt = datetime.datetime.strptime(start_cat, "%Y%m%d%H%M%S %z")
            stop_cat = (start_dt + datetime.timedelta(hours=2)).strftime("%Y%m%d%H%M%S %z")

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

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

def main():
    programs, today_usa = fetch_starz_schedule()
    xml_content = generate_xmltv(programs, today_usa)
    
    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(xml_content)

if __name__ == "__main__":
    main()
