import os
with open("server.py", "r", encoding="utf-8") as f:
    server_code = f.read()
server_code = server_code.replace('db_path = "database.db"', 'db_path = "scams.db"')
with open("server.py", "w", encoding="utf-8") as f:
    f.write(server_code)
print("Updated server.py to point to scams.db")
