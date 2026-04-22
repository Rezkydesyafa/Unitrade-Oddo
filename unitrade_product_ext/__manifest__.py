{
    'name': 'UniTrade Product Extension',
    'version': '17.0.1.1.0',
    'summary': 'Extend products with condition, seller, location, specs, and custom detail page',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Website/Website',
    'depends': ['product', 'website_sale', 'unitrade_seller'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_views.xml',
        'views/product_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'unitrade_product_ext/static/src/css/product_detail.css',
            'unitrade_product_ext/static/src/js/product_detail.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
