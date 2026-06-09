{
    'name': 'UniTrade Customer Service AI',
    'version': '17.0.1.0.0',
    'summary': 'AI (Gemini) customer service chat with admin escalation',
    'description': """
        Customer Service berbantuan AI untuk UniTrade:
        - Widget chat CS (reuse UI unitrade_chat)
        - Jawaban otomatis Google Gemini (gemini-2.5-flash)
        - Eskalasi ke admin + integrasi tiket existing
        - Penanganan admin realtime via bus
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
        'unitrade_chat',
        'unitrade_admin',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cs_ai_config.xml',
        'views/cs_chat_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'unitrade_cs_ai/static/src/css/cs_chat.css',
            'unitrade_cs_ai/static/src/xml/cs_chat.xml',
            'unitrade_cs_ai/static/src/js/cs_chat.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
