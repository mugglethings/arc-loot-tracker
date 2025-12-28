import sqlite3

conn = sqlite3.connect(r"C:\code\ARCLTIE\loot_trackercopy.db")
cur = conn.cursor()

# Tjek eksisterende rækker i korrekt tabel
cur.execute("SELECT * FROM loot_items WHERE ITEM_NAME='Motor';")
print(cur.fetchall())

# Opdater posten
cur.execute("UPDATE loot_items SET ITEM_NAME='motor' WHERE ITEM_NAME='Motor';")
conn.commit()

# Bekræft ændring
cur.execute("SELECT * FROM loot_items WHERE ITEM_NAME='motor';")
print(cur.fetchall())

conn.close()
