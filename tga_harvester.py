import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
import uuid
import datetime
import re
import requests
from bs4 import BeautifulSoup

DB_PATH = "scams.db"

def fetch_tga_alerts():
    print("[TGA Harvester] Fetching latest alerts from TGA (Australia)...")
    url = "https://www.tga.gov.au/news/safety-alerts"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        # Standard connection without proxy due to Gov geo-blocks on datacenter IPs
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # We look for the main view container rows
        articles = soup.find_all('div', class_='views-row')
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        inserted = 0
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        
        for a in articles[:30]:
            title_el = a.find(['h2', 'h3'])
            if not title_el:
                continue
                
            title = title_el.text.strip()
            link_el = title_el.find('a')
            link = "https://www.tga.gov.au" + link_el['href'] if link_el and link_el.has_attr('href') else ""
            
            date_el = a.find('time')
            date_fmt = today_str
            if date_el and date_el.has_attr('datetime'):
                date_fmt = date_el['datetime'].split('T')[0]
                
            desc_el = a.find('div', class_='field-content')
            summary = desc_el.text.strip() if desc_el else title
            
            # Filter
            if not any(word in title.lower() for word in ["recall", "falsified", "fake", "safety alert", "defect"]):
                continue
            
            slug_clean = re.sub(r'[^a-zA-Z0-9]+', '-', title.split(':')[0].lower()).strip('-')[:30]
            slug = f"{slug_clean}-{str(uuid.uuid4()).split('-')[0]}"
            
            entity_name = title.split('-')[0][:100].strip()
            
            scam_type = "TGA Safety Alert"
            if "recall" in title.lower(): scam_type = "TGA Product Recall"
            elif "fake" in title.lower(): scam_type = "Counterfeit Medicine"
            
            danger_level = "High"
            
            try:
                c.execute('''
                    INSERT INTO regulatory_scam_reports 
                    (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (slug, entity_name, link, scam_type, danger_level, "ALERT", "TGA (Australia)", summary, date_fmt, today_str))
                inserted += 1
            except sqlite3.IntegrityError:
                pass
                
        conn.commit()
        conn.close()
        print(f"[TGA Harvester] Successfully inserted {inserted} new TGA alerts into scams.db!")
        
    except Exception as e:
        print(f"[TGA Harvester] Error: {e}")

if __name__ == "__main__":
    fetch_tga_alerts()
