import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
import uuid
import datetime
import re

DB_PATH = "scams.db"
PROXY_URL = "http://user_271de2bb43,sesstime_10080,session_ntn4v4z4i0:05e481@portal.anyip.io:1080"

def fetch_ema_alerts():
    print("[EMA Harvester] Fetching latest alerts from EMA via anyIP proxy...")
    
    # We will pull the main news RSS feed and filter for safety/recalls/falsified
    url = "https://www.ema.europa.eu/en/documents/rss/news-and-press-releases.xml"
    # Fallback to search if the above feed is different
    url = "https://www.ema.europa.eu/en/rss/news-and-press-releases.xml"
    
    # Actually let's use requests for proxy support easily
    import requests
    from bs4 import BeautifulSoup
    
    proxies = {"http": PROXY_URL, "https": PROXY_URL}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    # We scrape the actual news page if RSS is tricky, since anyIP allows us to bypass blocks
    search_url = "https://www.ema.europa.eu/en/news-events/news-and-press-releases?search_api_views_fulltext=falsified+OR+recall+OR+safety+alert"
    
    try:
        res = requests.get(search_url, proxies=proxies, headers=headers, timeout=20)
        
        if res.status_code == 404:
            # Fallback to general news url for the latest structure
            search_url = "https://www.ema.europa.eu/en/news-events/news"
            res = requests.get(search_url, proxies=proxies, headers=headers, timeout=20)
            
        print(f"Status: {res.status_code}")
        
        soup = BeautifulSoup(res.text, 'html.parser')
        articles = soup.find_all('div', class_='ecl-content-item')
        if not articles:
            articles = soup.find_all('article')
            
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        inserted = 0
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        
        for a in articles[:50]:
            title_el = a.find(['h2', 'h3'])
            if not title_el:
                continue
            title = title_el.text.strip()
            
            link_el = title_el.find('a')
            link = "https://www.ema.europa.eu" + link_el['href'] if link_el and link_el.has_attr('href') else ""
            
            # Filter for relevance
            if not any(word in title.lower() for word in ["recall", "falsified", "fake", "safety", "suspend", "withdraw"]):
                continue
                
            desc_el = a.find('div', class_='ecl-content-item__description') or a.find('div', class_='content')
            summary = desc_el.text.strip() if desc_el else title
            
            # Slug generation
            slug_base = title.split(':')[0] if ':' in title else title
            slug_clean = re.sub(r'[^a-zA-Z0-9]+', '-', slug_base.lower()).strip('-')[:30]
            slug = f"{slug_clean}-{str(uuid.uuid4()).split('-')[0]}"
            
            # Entity Name guess
            entity_name = title.split('(')[0][:100].strip()
            if "falsified" in entity_name.lower():
                entity_name = entity_name.replace("Falsified", "").replace("falsified", "").strip()
            
            scam_type = "EMA Safety Alert"
            if "recall" in title.lower():
                scam_type = "EMA Drug Recall"
            elif "falsified" in title.lower():
                scam_type = "Falsified/Fake Medicine (EU)"
                
            danger_level = "High"
            if "fatal" in summary.lower() or "death" in summary.lower() or "falsified" in title.lower():
                danger_level = "Critical"
                
            regulator = "EMA (Europe)"
            status = "RECALLED/ALERT"
            
            try:
                c.execute('''
                    INSERT INTO regulatory_scam_reports 
                    (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (slug, entity_name, link, scam_type, danger_level, status, regulator, summary, today_str, today_str))
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        
        conn.commit()
        conn.close()
        print(f"[EMA Harvester] Successfully inserted {inserted} new EMA alerts into scams.db!")
        
    except Exception as e:
        print(f"[EMA Harvester] Error: {e}")

if __name__ == "__main__":
    fetch_ema_alerts()
