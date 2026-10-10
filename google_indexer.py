import json
import sqlite3
import requests
import time
from google.oauth2 import service_account
import google.auth.transport.requests

# Configurari
KEYS = [
    "pill-bot-1-4d5f1834bade.json"
]
BASE_URL = "https://pillscamradar.com/scam/"
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]

def get_access_token(key_file):
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    request = google.auth.transport.requests.Request()
    creds.refresh(request)
    return creds.token

def get_urls_from_db():
    conn = sqlite3.connect("scams.db")
    cursor = conn.cursor()
    # Preluam doar ce nu e indexat
    cursor.execute("SELECT slug FROM regulatory_scam_reports WHERE is_indexed = 0 LIMIT 200")
    rows = cursor.fetchall()
    conn.close()
    
    urls = []
    # Add homepage doar daca vrem, dar pt daily mai bine lasam doar reporturile
    # urls.append("https://pillscamradar.com/")
    
    for row in rows:
        urls.append(BASE_URL + row[0])
    return urls

def run_indexer():
    urls = get_urls_from_db()
    print(f"Am gasit {len(urls)} URL-uri pentru indexare.")
    
    token = get_access_token(KEYS[0])
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    success = 0
    conn = sqlite3.connect("scams.db")
    cursor = conn.cursor()
    
    for url in urls:
        payload = {
            "url": url,
            "type": "URL_UPDATED"
        }
        res = requests.post(ENDPOINT, json=payload, headers=headers)
        if res.status_code == 200:
            print(f"[SUCCESS] {url}")
            success += 1
            slug = url.split("/")[-1]
            cursor.execute("UPDATE regulatory_scam_reports SET is_indexed = 1 WHERE slug = ?", (slug,))
            conn.commit()
        elif res.status_code == 429:
            print(f"[RATE LIMIT] Pauza 5 secunde...")
            time.sleep(5)
            # retry once
            res = requests.post(ENDPOINT, json=payload, headers=headers)
            if res.status_code == 200:
                print(f"[SUCCESS] {url}")
                success += 1
                slug = url.split("/")[-1]
                cursor.execute("UPDATE regulatory_scam_reports SET is_indexed = 1 WHERE slug = ?", (slug,))
                conn.commit()
            else:
                print(f"[ERROR] {url} - {res.text}")
        else:
            print(f"[ERROR] {url} - {res.text}")
            
    conn.close()
            
    print(f"\nFinalizat! {success} din {len(urls)} URL-uri indexate cu succes.")

if __name__ == "__main__":
    run_indexer()
