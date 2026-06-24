from db_connection import connect

conn = connect()
cur = conn.cursor()

# Kita sisakan ID 8 (yang ada OAuth UID-nya), dan ganti login untuk ID 6 dan 7
print("Memperbaiki akun duplikat...")
cur.execute("UPDATE res_users SET login = 'rezkydesyafa_dup1@gmail.com', active = false WHERE id = 6")
cur.execute("UPDATE res_users SET login = 'rezkydesyafa_dup2@gmail.com', active = false WHERE id = 7")
conn.commit()

# Verifikasi
cur.execute("SELECT id, login, active FROM res_users WHERE id IN (6, 7, 8)")
for user in cur.fetchall():
    print(f"ID: {user[0]}, Login: {user[1]}, Active: {user[2]}")

conn.close()
print("Selesai! Sekarang hanya ada 1 akun utama dengan email tersebut.")
