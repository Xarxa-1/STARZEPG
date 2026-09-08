import json
import re
import sys
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
from bs4 import BeautifulSoup
import pytz

# Zones horàries exactes: Nova York (EDT / UTC-4) i Catalunya (CEST / UTC+2)
TZ_NY = pytz.timezone("America/New_York")
TZ_CAT = pytz.timezone("Europe/Madrid")

def parse_time_string(time_str):
    """
    Converteix textos com '11:22 AM' o '1:21 PM' a un objecte datetime.time.
    """
    time_str = time_str.strip().upper()
    return datetime.datetime.strptime(time_str, "%I:%M %p").time()

def convert_range_ny_to_cat(time_range_str, base_date_ny):
    """
    Processa intervals com '11:22 AM - 1:21 PM' o '11:45 PM - 1:21 AM EST'.
    Suma exactament les 6 hores de diferència entre Nova York i Catalunya.
    """
    # Netejar el text i eliminar 'EST' o 'EDT'
    clean_str = re.sub(r'\b(EST|EDT)\b', '', time_range_str, flags=re.IGNORECASE).strip()
    
    parts = clean_str.split('-')
    if len(parts) != 2:
        # Fallback si no hi ha interval
        start_t = parse_time_string(clean_str)
        dt_start_ny = TZ_NY.localize(datetime.datetime.combine(base_date_ny.date(), start_t))
        dt_start_cat = dt_start_ny.astimezone(TZ_CAT)
        dt_stop_cat = dt_start_cat + datetime.timedelta(hours=2)
        return dt_start_cat.strftime("%Y%m%d%H%M%S %z"), dt_stop_cat.strftime("%Y%m%d%H%M%S %z")

    start_str, stop_str = parts[0].strip(), parts[1].strip()
    
    # Arreglar l'AM/PM de l'hora d'inici si no en té (ex: '11:22 - 1:21 PM')
    if not re.search(r'(AM|PM)', start_str, re.IGNORECASE):
        period = "PM" if "PM" in stop_str.upper() else "AM"
        start_str = f"{start_str} {period}"

    start_t = parse_time_string(start_str)
    stop_t = parse_time_string(stop_str)

    dt_start_ny = TZ_NY.localize(datetime.datetime.combine(base_date_ny.date(), start_t))
    
    # Si l'hora de fi és menor que la d'inici, ha passat de la mitjanit a NY
    stop_date = base_date_ny.date()
    if stop_t < start_t:
        stop_date += datetime.timedelta(days=1)
        
    dt_stop_ny = TZ_NY.localize(datetime.datetime.combine(stop_date, stop_t))

    # Conversió a l'horari de Catalunya (afegeix 6 hores exactes)
    dt_start_cat = dt_start_ny.astimezone(TZ_CAT)
    dt_stop_cat = dt_stop_ny.astimezone(TZ_CAT)

    return dt_start_cat.strftime("%Y%m%d%H%M%S %z"), dt_stop_cat.strftime("%Y%m%d%H%M%S %z")

def main():
    # Data actual a Nova York
    now_ny = datetime.datetime.now(TZ_NY)
    
    # Dades extretes de la graella de STARZ
    raw_schedule = [
        {"title": "Trouble Man", "time_range": "11:45 PM - 1:21 AM EST", "desc": "A PI gets hired to find a missing R&B star...", "rating": "TV-MA"},
        {"title": "Fightland S1 E6 - There Is a War Coming", "time_range": "1:21 - 2:18 AM EST", "desc": "Duke prepares for his long-awaited shot at revenge...", "rating": "TV-MA"},
        {"title": "Double Take", "time_range": "2:18 - 3:50 AM EST", "desc": "An investment banker is on the run to Mexico...", "rating": "PG-13"},
        {"title": "Date And Switch", "time_range": "3:50 - 5:25 AM EST", "desc": "Two high school seniors make a pact to lose their virginity...", "rating": "R"},
        {"title": "Scary Movie", "time_range": "5:25 - 6:55 AM EST", "desc": "Cindy and her friends are stalked by a masked killer...", "rating": "R"},
        {"title": "The Italian Job", "time_range": "6:55 - 8:50 AM EST", "desc": "Betrayed after a perfect heist, Charlie Croker teams with a safecracker...", "rating": "PG-13"},
        {"title": "Beast", "time_range": "8:50 - 10:45 AM EST", "desc": "When his brother is at risk, a former MMA champ steps back into the ring...", "rating": "R"},
        {"title": "Non-Stop", "time_range": "10:45 AM - 12:35 PM EST", "desc": "U.S. air marshal Bill Marks is thrust into a crisis...", "rating": "PG-13"},
        {"title": "Scary Movie", "time_range": "12:35 - 2:05 PM EST", "desc": "Cindy and her friends are stalked by a masked killer...", "rating": "R"},
        {"title": "Scary Movie 2", "time_range": "2:05 - 3:30 PM EST", "desc": "Cindy and her friends sign up for a sleep study...", "rating": "R"},
        {"title": "Scary Movie 3", "time_range": "3:30 - 4:55 PM EST", "desc": "Cindy must stop a deadly videotape curse...", "rating": "PG-13"},
        {"title": "Beast", "time_range": "4:55 - 6:50 PM EST", "desc": "When his brother is at risk, a former MMA champ steps back into the ring...", "rating": "R"},
        {"title": "Resurrection Road", "time_range": "6:50 - 8:10 PM EST", "desc": "Six soldiers infiltrate a Confederate fort in Arkansas...", "rating": "R"},
        {"title": "Fightland S1 E6 - There Is a War Coming", "time_range": "8:10 - 9:05 PM EST", "desc": "Duke prepares for his long-awaited shot at revenge...", "rating": "TV-MA"},
        {"title": "The Italian Job", "time_range": "9:05 - 11:00 PM EST", "desc": "Betrayed after a perfect heist, Charlie Croker teams with a safecracker...", "rating": "PG-13"},
        {"title": "Non-Stop", "time_range": "11:00 PM - 12:50 AM EST", "desc": "U.S. air marshal Bill Marks is thrust into a crisis...", "rating": "PG-13"}
    ]

    tv = ET.Element("tv", {"generator-info-name": "STARZ-EPG-Scraper-Exact-CAT"})
    
    channel = ET.SubElement(tv, "channel", id="starz-stz1")
    display_name = ET.SubElement(channel, "display-name")
    display_name.text = "STARZ STZ1"

    for item in raw_schedule:
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

    rough_string = ET.tostring(tv, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    xml_content = reparsed.toprettyxml(indent="  ")

    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(xml_content)

if __name__ == "__main__":
    main()
