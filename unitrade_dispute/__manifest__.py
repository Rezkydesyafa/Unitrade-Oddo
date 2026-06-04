{
    'name': 'UniTrade Dispute',
    'version': '17.0.1.0.0',
    'summary': 'Refund and dispute workflow for UniTrade escrow orders',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Sales',
    'depends': ['sale', 'website', 'portal', 'unitrade_payment', 'unitrade_theme', 'unitrade_seller'],
    'data': [
        'security/ir.model.access.csv',
        'data/refund_config.xml',
        'data/mail_templates.xml',
        'views/refund_templates.xml',
        'views/dispute_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'unitrade_dispute/static/src/css/refund.css',
            'unitrade_dispute/static/src/js/refund.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
