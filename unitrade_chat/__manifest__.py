{
    'name': 'UniTrade Chat',
    'version': '17.0.1.0.0',
    'summary': 'Buyer-seller product chat for UniTrade Marketplace',
    'description': """
        Internal buyer-seller chat for UniTrade:
        - Product-aware conversations
        - OWL chat interface
        - Realtime updates via Odoo bus
        - Image and product preview messages
    """,
    'author': 'Tim 1 - UNISA Yogyakarta',
    'website': 'https://unitrade.dev',
    'category': 'Website',
    'depends': [
        'website',
        'portal',
        'mail',
        'bus',
        'unitrade_theme',
        'unitrade_seller',
        'unitrade_product_ext',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/chat_templates.xml',
        'views/chat_report_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'unitrade_chat/static/src/css/chat.css',
            'unitrade_chat/static/src/xml/chat.xml',
            'unitrade_chat/static/src/js/chat.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
