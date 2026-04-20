{
    'name': 'UniTrade Payment',
    'version': '17.0.1.0.0',
    'summary': 'Midtrans payment gateway integration',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Accounting/Payment',
    'depends': ['sale', 'account', 'payment'],
    'data': [
        'security/ir.model.access.csv',
        'views/payment_views.xml',
        'views/checkout_templates.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
