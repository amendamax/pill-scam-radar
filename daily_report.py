import sqlite3
import ctypes
import datetime

conn = sqlite3.connect('scams.db')
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM regulatory_scam_reports")
total = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM regulatory_scam_reports WHERE is_indexed = 0")
unindexed = cursor.fetchone()[0]

today_str = datetime.date.today().strftime("%Y-%m-%d")
cursor.execute("SELECT COUNT(*) FROM regulatory_scam_reports WHERE discovered_date = ?", (today_str,))
added_today = cursor.fetchone()[0]

conn.close()

message = (
    f"[ PillScamRadar - Raport Zilnic ]\n\n"
    f"Total Inregistrari in Baza: {total}\n"
    f"Alerte NOI adaugate azi: {added_today}\n"
    f"Pagini in asteptare (pentru Indexare Google): {unindexed}\n\n"
    f"Nota: Paginile in asteptare sunt indexate in siguranta si prin metoda clasica (Directory SEO) fara sa ne bazam doar pe API."
)

# Print for logs safely
print(message.encode('ascii', 'ignore').decode('ascii'))

# Alert Box
ctypes.windll.user32.MessageBoxW(0, message, "PillScamRadar Status", 0x40 | 0x0)
