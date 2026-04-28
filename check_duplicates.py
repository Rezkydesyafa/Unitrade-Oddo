import psycopg2

conn = psycopg2.connect(dbname='unitrade_db', user='openpg', password='admin', host='localhost', port=5432)
cur = conn.cursor()

print("Mencari duplikat login di tabel res_users...")
cur.execute("""
    SELECT login, COUNT(*) 
    FROM res_users 
    GROUP BY login 
    HAVING COUNT(*) > 1
""")
duplicates = cur.fetchall()

if not duplicates:
    print("Tidak ada duplikat login yang ditemukan.")
else:
    for dup in duplicates:
        login = dup[0]
        count = dup[1]
        print(f"\nLogin '{login}' digunakan oleh {count} akun. Detail:")
        
        cur.execute("SELECT id, partner_id, active, oauth_uid FROM res_users WHERE login = %s", (login,))
        for user in cur.fetchall():
            print(f"  - ID: {user[0]}, Partner ID: {user[1]}, Active: {user[2]}, OAuth UID: {user[3]}")

conn.close()
