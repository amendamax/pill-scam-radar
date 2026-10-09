import sqlite3
import requests
import uuid
import datetime
import json
import time

db_path = "scams.db"

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS regulatory_scam_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    entity_name TEXT NOT NULL,
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

c.execute("DELETE FROM regulatory_scam_reports")

print("Fetching data from OpenFDA API...")

batch = []
urls = [
    'https://api.fda.gov/drug/enforcement.json?search=reason_for_recall:"unapproved"+OR+reason_for_recall:"sildenafil"+OR+reason_for_recall:"sibutramine"+OR+reason_for_recall:"tainted"&limit=1000'
]

today_str = datetime.date.today().strftime("%Y-%m-%d")
total_fetched = 0

for url in urls:
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        results = data.get("results", [])
        total_fetched += len(results)
        
        for item in results:
            entity_name = item.get("recalling_firm", "Unknown Firm")
            raw_desc = item.get("product_description", "Unknown Product")
            
            # Create a slug from firm and random hash
            clean_firm = "".join(e for e in entity_name if e.isalnum()).lower()
            slug = f"{clean_firm}-{str(uuid.uuid4()).split('-')[0]}"
            
            domain_url = item.get("city", "") + ", " + item.get("state", "") + " (FDA Recall)"
            scam_type = "Unapproved/Tainted Drug"
            if "sildenafil" in raw_desc.lower() or "tadalafil" in raw_desc.lower():
                scam_type = "Tainted Male Enhancement"
            elif "sibutramine" in raw_desc.lower() or "weight loss" in raw_desc.lower():
                scam_type = "Tainted Weight Loss Pill"
                
            # Class I is most severe
            class_str = item.get("classification", "")
            if "Class I" in class_str and "Class II" not in class_str:
                severity = "CRITICAL"
            elif "Class II" in class_str:
                severity = "HIGH"
            else:
                severity = "MEDIUM"
                
            status_api = item.get("status", "Recalled")
            if status_api == "Terminated":
                status = "RECALL TERMINATED"
            else:
                status = "SCAM/RECALL ACTIVE"
                
            regulator = "FDA (USA) - OpenFDA"
            description = f"FDA RECALL: {item.get('reason_for_recall', '')} | PRODUCT: {raw_desc}"
            
            raw_date = item.get("recall_initiation_date", "")
            if len(raw_date) == 8:
                disc_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            else:
                disc_date = today_str
                
            batch.append((slug, entity_name, domain_url, scam_type, severity, status, regulator, description, disc_date, today_str))

    else:
        print(f"Error fetching: {response.status_code}")
    time.sleep(1)

# Ensure uniqueness by dropping duplicates on slug if any (uuid usually handles it, but just in case)
c.executemany("INSERT INTO regulatory_scam_reports (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)

conn.commit()
conn.close()

print(f"scams.db successfully generated with {total_fetched} real FDA enforcement records!")

# Modify server.py to point to scams.db instead of database.db
with open("server.py", "r") as f:
    server_code = f.read()
    
server_code = server_code.replace('db_path = "database.db"', 'db_path = "scams.db"')
with open("server.py", "w") as f:
    f.write(server_code)

print("Updated server.py to point to scams.db")
