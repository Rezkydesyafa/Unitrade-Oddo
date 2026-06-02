{
    'name': 'UniTrade Payment',
    'version': '17.0.1.0.0',
    'summary': 'Midtrans payment gateway integration',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Accounting/Payment',
    'depends': ['sale', 'account', 'payment'],
    'data': [
        'security/ir.model.access.csv',
<<<<<<< HEAD
        'views/payment_views.xml',
=======
        'data/midtrans_config.xml',
        'data/payment_runtime_config.xml',
        'data/voucher_data.xml',
        'data/mail_templates.xml',
        'data/escrow_cron.xml',
        'data/listing_fee_expiry_cron.xml',
        'data/seller_payout_sequence.xml',
        'views/payment_views.xml',
        'views/voucher_views.xml',
        'views/seller_payout_views.xml',
>>>>>>> ca9bf47 (feat : admin fajar anjay sadboy)
        'views/checkout_templates.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
