{
    'name': 'UniTrade Payment',
    'version': '17.0.1.0.0',
    'summary': 'Midtrans Core internal checkout, escrow ledger, and seller payout',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Accounting/Payment',
    'depends': ['sale', 'account', 'payment', 'website_sale', 'unitrade_seller', 'unitrade_theme'],
    'data': [
        'security/ir.model.access.csv',
        'data/midtrans_config.xml',
        'data/payment_runtime_config.xml',
        'data/mail_templates.xml',
        'views/payment_views.xml',
        'views/checkout_templates.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
