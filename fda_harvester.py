import datetime
import os
import re
import sqlite3
import requests

DB_PATH = "/var/data/scams.db" if os.path.exists("/var/data") else "scams.db"


def fetch_fda_alerts():
    print(f"[FDA Harvester] Fetching latest tainted & unapproved drug recalls into {DB_PATH}...")
    url = (
        'https://api.fda.gov/drug/enforcement.json?'
        'search=reason_for_recall:"unapproved"+OR+reason_for_recall:"sildenafil"'
        '+OR+reason_for_recall:"sibutramine"+OR+reason_for_recall:"tainted"&limit=100'
    )
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    try:
        response = requests.get(url, timeout=20)
        if response.status_code != 200:
            print(f"[FDA Harvester] HTTP {response.status_code}")
            return 0

        results = response.json().get("results", [])
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        c = conn.cursor()
        inserted = 0

        for item in results:
            recall_num = (item.get("recall_number") or "").strip()
            firm = (item.get("recalling_firm") or "Unknown Firm").strip()
            raw_desc = (item.get("product_description") or "Unknown Product").strip()
            prod_short = raw_desc.split(",")[0].split("(")[0].strip()[:80]
            entity_name = f"{prod_short} ({firm})"[:120] if prod_short else firm[:120]

            if recall_num:
                slug = re.sub(r"[^a-z0-9-]+", "-", recall_num.lower()).strip("-")
            else:
                slug = re.sub(r"[^a-z0-9-]+", "-", entity_name.lower()).strip("-")[:50]

            city = item.get("city", "")
            state = item.get("state", "")
            domain_url = f"FDA Recall #{recall_num}" if recall_num else f"{city}, {state} (FDA Recall)"

            low_desc = (raw_desc + " " + item.get("reason_for_recall", "")).lower()
            if "sildenafil" in low_desc or "tadalafil" in low_desc:
                scam_type = "Tainted Male Enhancement"
            elif "sibutramine" in low_desc or "weight loss" in low_desc:
                scam_type = "Tainted Weight Loss Pill"
            elif "dietary" in low_desc:
                scam_type = "Dietary Supplement"
            else:
                scam_type = "Unapproved/Tainted Drug"

            class_str = item.get("classification", "")
            if "Class I" in class_str and "Class II" not in class_str:
                severity = "CRITICAL"
            elif "Class II" in class_str:
                severity = "HIGH"
            else:
                severity = "MEDIUM"

            status_api = item.get("status", "Recalled")
            status = "RECALL TERMINATED" if status_api == "Terminated" else "SCAM/RECALL ACTIVE"
            regulator = item.get("code_info") or "FDA (USA) - OpenFDA"
            description = f"FDA RECALL: {item.get('reason_for_recall', '')} | PRODUCT: {raw_desc}"

            raw_date = item.get("recall_initiation_date", "")
            disc_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) == 8 else today_str

            try:
                c.execute(
                    """
                    INSERT OR IGNORE INTO regulatory_scam_reports
                    (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (slug, entity_name, domain_url, scam_type, severity, status, regulator[:250], description, disc_date, today_str),
                )
                if c.rowcount > 0:
                    inserted += 1
            except sqlite3.Error:
                pass

        conn.commit()
        conn.close()
        print(f"[FDA Harvester] Inserted {inserted} new FDA enforcement records.")
        return inserted
    except Exception as e:
        print(f"[FDA Harvester] Error: {e}")
        return 0


if __name__ == "__main__":
    fetch_fda_alerts()
