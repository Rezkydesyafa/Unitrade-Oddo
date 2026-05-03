{
    'name': 'UniTrade Review',
    'version': '17.0.1.0.0',
    'summary': 'Product rating and review system',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Website',
    'depends': ['sale', 'unitrade_product_ext'],
    'data': [
        'security/ir.model.access.csv',
        'views/review_views.xml',
        'views/review_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'unitrade_review/static/src/css/review_backend.css',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
