{
    'name': 'UniTrade Notification',
    'version': '17.0.1.0.0',
    'summary': 'System notifications for orders, payments, and deliveries',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Website',
    'depends': ['mail', 'unitrade_payment', 'unitrade_delivery'],
    'data': [
        'security/ir.model.access.csv',
        'views/notification_templates.xml',
        'data/mail_template.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
