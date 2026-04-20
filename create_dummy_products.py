import sys
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', r'C:\Program Files\Odoo 17.0.20260217\server\odoo.conf', '-d', 'unitrade_db'])
registry = odoo.registry('unitrade_db')

with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env['product.template']
    
    products = [
        {'name': 'Sepatu Converse Bekas', 'list_price': 250000.0, 'is_published': True, 'detailed_type': 'consu'},
        {'name': 'Kamera Mirrorless Sony', 'list_price': 5500000.0, 'is_published': True, 'detailed_type': 'consu'},
        {'name': 'Buku Kuliah Manajemen', 'list_price': 85000.0, 'is_published': True, 'detailed_type': 'consu'},
        {'name': 'Kemeja Flanel Uniqlo', 'list_price': 120000.0, 'is_published': True, 'detailed_type': 'consu'},
        {'name': 'Helm Bogo Retro', 'list_price': 150000.0, 'is_published': True, 'detailed_type': 'consu'},
    ]
    
    count = 0
    for p in products:
        if not Product.search([('name', '=', p['name'])]):
            Product.create(p)
            count += 1
            
    print(f"Created {count} dummy products.")
