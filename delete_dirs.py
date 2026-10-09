import os
import shutil

dirs_to_delete = ["de", "es", "fr", "it", "pt", "ro", "ru", "articles", "isbrokersafe-sdk", "verifydating-sdk", "backups", "uploads", "keys", "__pycache__", "broker-verifier", ".git"]

for d in dirs_to_delete:
    if os.path.exists(d):
        try:
            shutil.rmtree(d)
            print(f"Deleted {d}")
        except Exception as e:
            print(f"Failed to delete {d}: {e}")
