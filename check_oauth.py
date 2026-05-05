from db_connection import connect

conn = connect()
cur = conn.cursor()

cur.execute("SELECT id, name, client_id, enabled, auth_endpoint FROM auth_oauth_provider WHERE enabled = true")
for row in cur.fetchall():
    print(f"ID={row[0]}  Name={row[1]}  Enabled={row[3]}")
    print(f"  Client ID: [{row[2]}]")
    print(f"  Auth URL: {row[4]}")
    print()

conn.close()
