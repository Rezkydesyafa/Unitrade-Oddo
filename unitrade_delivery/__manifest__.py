{
    'name': 'UniTrade Delivery',
    'version': '17.0.1.0.0',
    'summary': 'GoSend delivery integration with GPS tracking',
    'author': 'Tim 1 - UNISA Yogyakarta',
    'category': 'Inventory/Delivery',
    'depends': ['sale', 'unitrade_payment'],
    'data': [
        'security/ir.model.access.csv',
        'views/delivery_views.xml',
        'views/delivery_templates.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
