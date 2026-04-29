{
    'name': 'UniTrade Seller',
    'version': '17.0.1.0.0',
    'summary': 'Seller verification with KTM OCR and OTP system',
    'description': """
        UniTrade Seller Module:
        - Seller registration and KTM verification
        - PaddleOCR integration for automatic KTM text extraction
        - OTP email verification for user accounts
        - Seller status workflow: draft → pending → verified / rejected
        - Admin verification dashboard
    """,
    'author': 'Tim 1 - UNISA Yogyakarta',
    'website': 'https://unitrade.dev',
    'category': 'Website',
    'depends': ['base', 'website', 'sale', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'data/demo_students.xml',
        'views/seller_views.xml',
        'views/seller_templates.xml',
        'views/seller_menus.xml',
        'views/seller_verification_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
