import json
import sqlite3
import requests
import time
import glob
from google.oauth2 import service_account
import google.auth.transport.requests

BASE_URL = "https://pillscamradar.com/scam/"
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]

def get_access_token(key_file):
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    request = google.auth.transport.requests.Request()
    creds.refresh(request)
    return creds.token

def get_urls_from_db(limit):
    conn = sqlite3.connect("scams.db")
    cursor = conn.cursor()
    cursor.execute("SELECT slug FROM regulatory_scam_reports WHERE is_indexed = 0 LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    urls = []
    for row in rows:
        urls.append(BASE_URL + row[0])
    return urls

def run_indexer():
    # Find all google service account keys in the directory
    # Except those ignored by git like config.json
    keys = [f for f in glob.glob("*.json") if "bot" in f or "indexer" in f or "scam" in f]
    
    if not keys:
        print("Nu s-au gasit chei API (fisiere .json) in folder!")
        return
        
    print(f"Am gasit {len(keys)} chei API. Vom incerca sa indexam {len(keys) * 200} URL-uri...")
    
    urls = get_urls_from_db(len(keys) * 200)
    print(f"Am gasit {len(urls)} URL-uri neindexate in baza de date.")
    
    if not urls:
        print("Toate URL-urile sunt deja indexate!")
        return

    success_total = 0
    conn = sqlite3.connect("scams.db")
    cursor = conn.cursor()
    
    # Impartim URL-urile pentru fiecare cheie (200 per cheie)
    url_chunks = [urls[i:i + 200] for i in range(0, len(urls), 200)]
    
    for i, key_file in enumerate(keys):
        if i >= len(url_chunks):
            break
            
        chunk = url_chunks[i]
        print(f"\n---> Folosesc cheia: {key_file} pentru {len(chunk)} URL-uri...")
        
        try:
            token = get_access_token(key_file)
        except Exception as e:
            print(f"Eroare la citirea cheii {key_file}: {e}")
            continue
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        for url in chunk:
            payload = {
                "url": url,
                "type": "URL_UPDATED"
            }
            res = requests.post(ENDPOINT, json=payload, headers=headers)
            if res.status_code == 200:
                print(f"[SUCCESS] {url}")
                success_total += 1
                slug = url.split("/")[-1]
                cursor.execute("UPDATE regulatory_scam_reports SET is_indexed = 1 WHERE slug = ?", (slug,))
                conn.commit()
            elif res.status_code == 429:
                print(f"[RATE LIMIT] Limita atinsa pentru cheia {key_file}. Trecem la urmatoarea...")
                break # Oprim chunk-ul asta si trecem la urmatoarea cheie
            else:
                print(f"[ERROR] {url} - {res.text}")
            
    conn.close()
    print(f"\nFinalizat! {success_total} din {len(urls)} URL-uri indexate cu succes pe {len(keys)} chei.")

if __name__ == "__main__":
    run_indexer()
