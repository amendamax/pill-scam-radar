import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
import uuid
import datetime
import re

DB_PATH = "scams.db"

def fetch_mhra_alerts():
    print("[MHRA Harvester] Fetching latest drug/device alerts from GOV.UK...")
    url = "https://www.gov.uk/drug-device-alerts.atom"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', namespaces)
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            inserted = 0
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            
            for entry in entries:
                title_node = entry.find('atom:title', namespaces)
                title = title_node.text if title_node is not None else ""
                
                # Filter to process actual recalls or alerts, ignoring general notice lists
                if "field safety notices:" in title.lower() or "list of" in title.lower():
                    continue
                    
                link_node = entry.find('atom:link', namespaces)
                link = link_node.attrib['href'] if link_node is not None else ""
                
                pub_node = entry.find('atom:updated', namespaces)
                if pub_node is None:
                    pub_node = entry.find('atom:published', namespaces)
                published = pub_node.text if pub_node is not None else today_str
                
                summary_node = entry.find('atom:summary', namespaces)
                summary = summary_node.text if summary_node is not None else title
                
                # Extract date format YYYY-MM-DD
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', published)
                date_fmt = date_match.group(1) if date_match else today_str
                
                # Slug generation
                slug_base = title.split(':')[0] if ':' in title else title
                slug_clean = re.sub(r'[^a-zA-Z0-9]+', '-', slug_base.lower()).strip('-')[:30]
                slug = f"{slug_clean}-{str(uuid.uuid4()).split('-')[0]}"
                
                # Entity Name guess (before the first comma or colon)
                entity_name = title.split(',')[0].split(':')[0][:100]
                
                scam_type = "MHRA Safety Alert"
                if "recall" in title.lower():
                    scam_type = "MHRA Drug/Device Recall"
                elif "fake" in title.lower() or "falsified" in title.lower():
                    scam_type = "Falsified/Fake Medicine"
                    
                danger_level = "Medium"
                if "class 1" in title.lower() or "class i" in title.lower() or "fatal" in summary.lower():
                    danger_level = "Critical"
                elif "class 2" in title.lower() or "class ii" in title.lower():
                    danger_level = "High"
                    
                regulator = "MHRA (UK)"
                status = "ALERT/RECALL"
                
                try:
                    c.execute('''
                        INSERT INTO regulatory_scam_reports 
                        (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (slug, entity_name, link, scam_type, danger_level, status, regulator, summary, date_fmt, today_str))
                    inserted += 1
                except sqlite3.IntegrityError:
                    # Duplicate slug (unlikely with UUID) or other unique constraint
                    pass
            
            conn.commit()
            conn.close()
            print(f"[MHRA Harvester] Successfully inserted {inserted} new alerts into scams.db!")
            
            # Optional IndexNow ping if needed
            # try: ... except: ...
            
    except Exception as e:
        print(f"[MHRA Harvester] Error: {e}")

if __name__ == "__main__":
    fetch_mhra_alerts()
