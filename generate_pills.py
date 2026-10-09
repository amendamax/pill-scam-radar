import sqlite3
import random
import uuid
import datetime

db_path = "database.db"

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

pill_prefixes = ["Bio", "Keto", "Slim", "Vita", "Neuro", "Testo", "Alpha", "Derma", "Nutra", "Pharma", "Ultra", "Max", "Pro", "Mega", "Zen", "Pure"]
pill_suffixes = ["Burn", "Genix", "Plus", "Boost", "Max", "Cleanse", "Trim", "Fit", "Grow", "Flex", "Life", "Health", "Care", "Vital", "Form", "Gummies"]

scam_types = ["Weight Loss Scam", "Male Enhancement Fraud", "Fake CBD Gummies", "Miracle Cure Scam", "Skin Care Trial Trap", "Hair Growth Scam", "Fake Shark Tank Product", "Subscription Trap", "Counterfeit Pills"]

regulators = ["FDA (USA)", "EMA (Europe)", "MHRA (UK)", "TGA (Australia)", "Health Canada"]

print("Generating 10,000 Pill Scam entries...")
batch = []
today = datetime.date.today()

for i in range(10000):
    brand = random.choice(pill_prefixes) + random.choice(pill_suffixes) + " " + random.choice(["Gummies", "Pills", "Capsules", "Drops", "Complex", "Extract"])
    slug = brand.lower().replace(" ", "-") + "-" + str(uuid.uuid4()).split('-')[0]
    domain = slug + ".com"
    scam = random.choice(scam_types)
    sev = random.choice(["HIGH", "CRITICAL", "MEDIUM"])
    reg = random.choice(regulators)
    
    desc = f"WARNING: {brand} is a known {scam.lower()} operation. They use deceptive marketing, fake celebrity endorsements (like Shark Tank or Oprah), and forced continuity subscription traps to bill your credit card repeatedly. Do not consume these products as they may contain undisclosed pharmaceutical ingredients."
    
    disc_date = today - datetime.timedelta(days=random.randint(0, 365))
    
    batch.append((slug, brand, domain, scam, sev, "SCAM DETECTED", reg, desc, disc_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")))

c.executemany("INSERT INTO regulatory_scam_reports (slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)

conn.commit()
conn.close()

print("database.db generated with 10,000 entries!")
