import sqlite3
import requests
from bs4 import BeautifulSoup
import uuid
import datetime
import re

DB_PATH = "scams.db"
PROXY_URL = "http://user_271de2bb43,country_us:05e481@portal.anyip.io:1080"
proxies = {"http": PROXY_URL, "https": PROXY_URL}
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def fetch_who_alerts():
    print("[WHO Harvester] Fetching historical alerts from World Health Organization...")
    url = "https://www.who.int/teams/regulation-prequalification/incidents-and-SF/full-list-of-who-medical-product-alerts"
    
    try:
        res = requests.get(url, proxies=proxies, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        links = soup.find_all('a')
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        inserted = 0
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        
        for link in links:
            href = link.get('href', '')
            text = link.text.strip()
            if not text:
                continue
                
            if 'medical-product-alert' in href.lower() or 'medical-product-alert' in text.lower():
                if href.startswith('/'):
                    href = "https://www.who.int" + href
                elif not href.startswith('http'):
                    continue
                    
                title_parts = text.split('\n')
                title = title_parts[-1].strip() if len(title_parts) > 0 else text
                
                # Extract date if available
                date_str = today_str
                if len(title_parts) > 2:
                    try:
                        d = datetime.datetime.strptime(title_parts[0].strip(), "%d %B %Y")
                        date_str = d.strftime("%Y-%m-%d")
                    except:
                        pass
                
                # Slug generation
                slug_clean = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')[:40]
                slug = f"who-{slug_clean}-{str(uuid.uuid4()).split('-')[0]}"
                
                entity_name = title.split(':')[1].strip() if ':' in title else title[:100]
                
                scam_type = "WHO Falsified Medical Product Alert"
                danger_level = "Critical"
                regulator = "World Health Organization (WHO)"
                status = "GLOBAL ALERT"
                
                try:
                    c.execute('''
                        INSERT INTO regulatory_scam_reports 
                        (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated, is_indexed)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ''', (slug, entity_name, href, scam_type, danger_level, status, regulator, title, date_str, today_str))
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
            
        conn.commit()
        conn.close()
        print(f"[WHO Harvester] Successfully inserted {inserted} new WHO alerts into scams.db!")
        
    except Exception as e:
        print(f"[WHO Harvester] Error: {e}")

if __name__ == "__main__":
    fetch_who_alerts()
