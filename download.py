import datetime
import pytz
from playwright.sync_api import sync_playwright

TZ_NY = pytz.timezone("America/New_York")

def download_page():
    now_ny = datetime.datetime.now(TZ_NY)
    year = now_ny.strftime("%Y")
    month = now_ny.strftime("%m")
    day = now_ny.strftime("%d")
    url = f"https://www.starz.com/us/en/schedule/STZ1/{year}/{month}/{day}"

    print(f"Obrint la URL: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        try:
            # Carregar la pàgina i esperar 10 segons a que el JS renderitzi la graella
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print("Esperant que el JavaScript renderitzi la graella...")
            page.wait_for_timeout(10000) 
            
            # Fer un scroll cap avall per carregar tots els blocs
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(3000)

            html_content = page.content()
            
            with open("page.html", "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"Pàgina descarregada correctament ({len(html_content)} caràcters) a page.html")
            
        except Exception as e:
            print(f"Error descarregant la pàgina: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    download_page()
