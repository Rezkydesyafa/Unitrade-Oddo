{
    'name': 'UniTrade Notification',
    'version': '17.0.1.0.0',
    'summary': 'System notifications for orders, payments, and deliveries',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Website',
    'depends': [
        'mail',
        'auth_signup',
        'unitrade_theme',
        'unitrade_seller',
        'unitrade_payment',
        'unitrade_delivery',
        'unitrade_chat',
        'unitrade_review',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/notification_templates.xml',
        'data/mail_template.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
