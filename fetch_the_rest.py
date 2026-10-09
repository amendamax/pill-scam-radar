import sqlite3
import requests
import re
import time

DB_PATH = 'scams.db'
API_KEY = '8dCXiLiJ007u4WJ1bPUHxNDcnsyyueNkS07iHJJW'

def fetch_all_openfda():
    print("Fetching ABSOLUTELY EVERYTHING from OpenFDA Drug Enforcement using API Key...")
    all_data = []
    
    # We will paginate until we hit the end
    for skip in range(0, 26000, 1000):
        url = f'https://api.fda.gov/drug/enforcement.json?api_key={API_KEY}&search=report_date:[20120101+TO+20261231]&limit=1000&skip={skip}'
        resp = requests.get(url)
        if resp.status_code == 200:
            batch = resp.json().get('results', [])
            if not batch:
                break
            print(f" -> Fetched {len(batch)} recalls (skip={skip})")
            all_data.extend(batch)
        elif resp.status_code == 404:
            print(" -> Reached the end of the database.")
            break
        else:
            print(f" -> API Error: {resp.status_code} - {resp.text}")
            break
        time.sleep(0.3)
            
    print(f"\nTotal raw reports fetched: {len(all_data)}")
    return all_data

def parse_and_insert(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    inserted = 0
    for item in data:
        recall_number = item.get('recall_number', '')
        if not recall_number:
            continue
            
        slug = recall_number.lower().replace(' ', '-').replace('/', '-')
        name_desc = item.get('product_description', 'Unknown Product')
        name_match = re.match(r'^([^,]+)', name_desc)
        name = name_match.group(1).strip()[:100] if name_match else name_desc[:100]
        
        category = "FDA Drug Recall"
        reason_text = item.get('reason_for_recall', '').lower()
        if "unapproved" in reason_text: category = "Unapproved Drug"
        if "tainted" in reason_text: category = "Tainted Product"
        if "dietary" in reason_text or "dietary" in name_desc.lower(): category = "Dietary Supplement"
        if "labeling" in reason_text: category = "Labeling Error"
        if "cgmp" in reason_text or "manufacturing" in reason_text: category = "Manufacturing Defect"
        if "sterility" in reason_text: category = "Contamination"
            
        date_str = item.get('recall_initiation_date', '')
        date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if date_str and len(date_str) == 8 else "Unknown"
        
        danger_level = "Medium"
        if item.get('classification', '') == 'Class I': danger_level = "Critical"
        elif item.get('classification', '') == 'Class II': danger_level = "High"
            
        active_ingredients = item.get('code_info', 'N/A')[:200]
        recalling_firm = item.get('recalling_firm', 'Unknown Firm')
        reason = item.get('reason_for_recall', '')
        domain_url = f"FDA Recall #{recall_number}"
        
        try:
            c.execute('''
                INSERT INTO regulatory_scam_reports 
                (slug, entity_name, scam_type, severity_level, discovered_date, domain_url, regulator_warnings, status, description, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (slug, name, category, danger_level, date_fmt, domain_url, active_ingredients, "Banned", reason, date_fmt))
            inserted += 1
        except sqlite3.IntegrityError:
            pass # already exists
            
    conn.commit()
    conn.close()
    print(f"Successfully inserted {inserted} NEW pill scams into the database!")

if __name__ == '__main__':
    data = fetch_all_openfda()
    if data:
        parse_and_insert(data)
