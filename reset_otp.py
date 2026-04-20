import psycopg2

conn = psycopg2.connect(dbname='unitrade_db', user='openpg', password='admin', host='localhost', port=5432)
cur = conn.cursor()

# Show all users
cur.execute("SELECT id, login, is_otp_verified FROM res_users WHERE login != '__system__' ORDER BY id")
for row in cur.fetchall():
    print(f"ID={row[0]}  login={row[1]}  verified={row[2]}")

# Reset ALL non-admin users
cur.execute("UPDATE res_users SET is_otp_verified = FALSE WHERE login != '__system__' AND login != 'admin'")
conn.commit()

print("\nAll non-admin users reset to is_otp_verified=False")
conn.close()
