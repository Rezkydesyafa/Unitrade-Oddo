-- Force add missing columns to res_users.
-- Pakai jika upgrade unitrade_theme tidak menambah kolom otomatis.
--
-- Cara jalankan (CMD as Admin):
--   "C:\Program Files\Odoo 17.0.20260217\PostgreSQL\bin\psql.exe" ^
--     -h localhost -U <user> -d unitrade_db -f force_add_columns.sql
--
-- Password DB: cek `odoo.conf` baris `db_password`.
-- Default: openpg / admin

ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_notify_all boolean DEFAULT true;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_notify_transaction boolean DEFAULT true;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_notify_promo boolean DEFAULT true;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_terms_privacy_accepted boolean DEFAULT false;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_terms_privacy_accepted_at timestamp;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_terms_privacy_version varchar;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_terms_privacy_ip varchar;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_terms_privacy_user_agent varchar;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_privacy_deactivated boolean DEFAULT false;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_privacy_deactivated_at timestamp;
ALTER TABLE res_users ADD COLUMN IF NOT EXISTS x_privacy_anonymized_ref varchar;

-- Verifikasi
SELECT column_name FROM information_schema.columns
WHERE table_name='res_users' AND column_name LIKE 'x_%'
ORDER BY column_name;
