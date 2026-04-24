import psycopg2

conn = psycopg2.connect(dbname='unitrade_db', user='openpg', password='admin')
cur = conn.cursor()

# Get all x_ fields that exist on product.template
cur.execute("""
    SELECT f.name 
    FROM ir_model_fields f 
    JOIN ir_model m ON f.model_id = m.id 
    WHERE m.model = 'product.template' AND f.name LIKE 'x_%'
    ORDER BY f.name
""")
existing = [r[0] for r in cur.fetchall()]
print("Existing x_ fields on product.template:")
for f in existing:
    print(f"  - {f}")

# Fields used in template
used = [
    'x_average_rating', 'x_review_count', 'x_specification',
    'x_condition', 'x_brand', 'x_weight_product',
    'x_seller_location', 'x_seller_latitude', 'x_seller_longitude',
    'x_seller_id', 'x_is_marketplace'
]
print("\nFields used in template vs existence:")
for f in used:
    status = "EXISTS" if f in existing else "MISSING"
    print(f"  {status}: {f}")
