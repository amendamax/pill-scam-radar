import sqlite3
import requests
import re

DB_PATH = 'scams.db'

def fetch_openfda():
    print("Fetching OpenFDA data for tainted supplements and unapproved drugs...")
    url = 'https://api.fda.gov/drug/enforcement.json?search=reason_for_recall:"tainted"+OR+reason_for_recall:"unapproved"+OR+product_description:"dietary+supplement"&limit=1000'
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Error: {resp.status_code}")
        return []
    data = resp.json().get('results', [])
    print(f"Found {len(data)} reports.")
    return data

def parse_and_insert(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # ensure table exists
    c.execute('''
    CREATE TABLE IF NOT EXISTS regulatory_scam_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE,
        entity_name TEXT,
        domain_url TEXT,
        scam_type TEXT,
        severity_level TEXT,
        status TEXT,
        regulator_warnings TEXT,
        description TEXT,
        discovered_date TEXT,
        last_updated TEXT
    )
    ''')
    
    inserted = 0
    for item in data:
        recall_number = item.get('recall_number', '')
        if not recall_number:
            continue
            
        slug = recall_number.lower().replace(' ', '-').replace('/', '-')
        
        name_desc = item.get('product_description', 'Unknown Product')
        name_match = re.match(r'^([^,]+)', name_desc)
        name = name_match.group(1).strip()[:100] if name_match else name_desc[:100]
        
        category = "Dietary Supplement"
        if "tainted" in item.get('reason_for_recall', '').lower():
            category = "Tainted Product"
            
        date_str = item.get('recall_initiation_date', '')
        if date_str and len(date_str) == 8:
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        else:
            date_fmt = "Unknown"
            
        danger_level = "High"
        if item.get('classification', '') == 'Class I':
            danger_level = "Critical"
        elif item.get('classification', '') == 'Class III':
            danger_level = "Medium"
            
        active_ingredients = item.get('code_info', 'N/A')[:200]
        recalling_firm = item.get('recalling_firm', 'Unknown Firm')
        reason = item.get('reason_for_recall', '')
        
        domain_url = f"FDA Recall #{recall_number}"
        
        try:
            c.execute('''
                INSERT INTO regulatory_scam_reports 
                (slug, entity_name, scam_type, severity_level, discovered_date, domain_url, regulator_warnings, status, description, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                slug,
                name,
                category,
                danger_level,
                date_fmt,
                domain_url,
                active_ingredients,
                "Banned",
                reason,
                date_fmt
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            pass # already exists
            
    conn.commit()
    conn.close()
    print(f"Successfully inserted {inserted} new pill scams into the database!")

if __name__ == '__main__':
    data = fetch_openfda()
    if data:
        parse_and_insert(data)
