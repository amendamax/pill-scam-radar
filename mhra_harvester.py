import datetime
import os
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET

DB_PATH = "/var/data/scams.db" if os.path.exists("/var/data") else "scams.db"


def fetch_mhra_alerts():
    print(f"[MHRA Harvester] Fetching latest drug/device alerts from GOV.UK into {DB_PATH}...")
    url = "https://www.gov.uk/drug-device-alerts.atom"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            namespaces = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", namespaces)

            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            c = conn.cursor()
            inserted = 0
            today_str = datetime.date.today().strftime("%Y-%m-%d")

            for entry in entries:
                title_node = entry.find("atom:title", namespaces)
                title = (title_node.text if title_node is not None else "").strip()
                if not title or "field safety notices" in title.lower() or "list of" in title.lower():
                    continue

                link_node = entry.find("atom:link", namespaces)
                link = link_node.attrib.get("href", "") if link_node is not None else ""

                pub_node = entry.find("atom:updated", namespaces) or entry.find("atom:published", namespaces)
                published = pub_node.text if pub_node is not None else today_str
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", published)
                date_fmt = date_match.group(1) if date_match else today_str

                summary_node = entry.find("atom:summary", namespaces)
                summary = (summary_node.text if summary_node is not None else title).strip()

                if link and "/" in link:
                    slug = re.sub(r"[^a-z0-9-]+", "-", link.rstrip("/").split("/")[-1].lower()).strip("-")[:75]
                else:
                    slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:75]

                entity_name = title[:120]
                scam_type = "MHRA Safety Alert"
                if "recall" in title.lower():
                    scam_type = "MHRA Drug/Device Recall"
                elif "fake" in title.lower() or "falsified" in title.lower():
                    scam_type = "Falsified/Fake Medicine"

                danger_level = "HIGH"
                if "class 1" in title.lower() or "class i" in title.lower() or "fatal" in summary.lower():
                    danger_level = "CRITICAL"

                try:
                    c.execute(
                        """
                        INSERT OR IGNORE INTO regulatory_scam_reports
                        (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (slug, entity_name, link, scam_type, danger_level, "ALERT/RECALL", "MHRA (UK)", summary, date_fmt, today_str),
                    )
                    if c.rowcount > 0:
                        inserted += 1
                except sqlite3.Error:
                    pass

            conn.commit()
            conn.close()
            print(f"[MHRA Harvester] Inserted {inserted} new MHRA alerts.")
            return inserted
    except Exception as e:
        print(f"[MHRA Harvester] Error: {e}")
        return 0


if __name__ == "__main__":
    fetch_mhra_alerts()
