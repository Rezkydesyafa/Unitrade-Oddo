{
    'name': 'UniTrade Product Extension',
    'version': '17.0.1.0.0',
    'summary': 'Extend products with condition, seller, and location fields',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Website/Website',
    'depends': ['product', 'website_sale', 'unitrade_seller'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_views.xml',
        'views/product_templates.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
