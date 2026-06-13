# 04. Code Map, Class, Route, dan Functions

Dokumen ini adalah peta belajar kode. Fokusnya: module mana berisi class apa, route mana memanggil function apa, service apa yang terlibat, dan function mana yang perlu dibaca untuk memahami fitur.

## Cara Membaca Function Di Odoo

Saat membaca function, tanyakan:

1. Function ini dipanggil dari route, tombol admin, cron, hook, atau function lain?
2. Function ini membaca data saja atau mengubah data?
3. Model/tabel apa yang berubah?
4. Apakah ada validasi akses?
5. Apakah ada notifikasi atau audit log setelahnya?
6. Apakah function memakai `sudo()`?
7. Apakah function punya efek ke module lain?

Pola nama function yang sering muncul:

| Pola | Arti |
| --- | --- |
| `_compute_...` | Menghitung field otomatis |
| `_check_...` | Validasi aturan |
| `_prepare_...` | Menyiapkan data sebelum simpan/tampil |
| `_format_...` | Mengubah tampilan data, misalnya uang/waktu |
| `_payload...` | Menyiapkan data untuk frontend/API |
| `action_...` | Aksi bisnis dari tombol/model |
| `create` | Saat record dibuat |
| `write` | Saat record diubah |
| `unlink` | Saat record dihapus |
| `cron_...` | Job otomatis |

## Route Index

### User/Public

| URL/route | Fungsi | Lokasi |
| --- | --- | --- |
| `/` | Homepage | `unitrade_theme/controllers/controllers.py` |
| `/shop` | Shop | `unitrade_theme`, `unitrade_product_ext` |
| `/shop/<slug>` | Detail produk | `unitrade_theme`, `unitrade_product_ext`, `unitrade_review` |
| `/shop/cart` | Keranjang | `unitrade_theme/controllers/cart.py` |
| `/shop/checkout`, `/shop/address` | Checkout alamat/pengiriman | `unitrade_theme/controllers/checkout.py` |
| `/shop/payment` | Payment page | `unitrade_theme/controllers/checkout.py` |
| `/unitrade/checkout/pay` | Proses bayar | `unitrade_theme/controllers/checkout.py`, `unitrade_payment` |
| `/unitrade/order/status/<order_id>` | Status order | `unitrade_payment/controllers/main.py` |
| `/my/account` | Profile | `unitrade_theme/controllers/controllers.py` |
| `/my/wishlist`, `/unitrade/wishlist` | Wishlist | `unitrade_wishlist/controllers/main.py` |
| `/my/notifications` | Notifikasi user | `unitrade_notification/controllers/main.py` |
| `/unitrade/chat` | Chat buyer | `unitrade_chat/controllers/main.py` |
| `/customer-service/chat/session` | CS AI session | `unitrade_cs_ai/controllers/cs_portal.py` |

### Seller

| URL/route | Fungsi | Lokasi |
| --- | --- | --- |
| `/seller-onboarding` | Awal onboarding seller | `unitrade_seller/controllers/seller_verification.py` |
| `/seller-verification` | Upload KTM | `unitrade_seller/controllers/seller_verification.py` |
| `/unitrade/seller/dashboard` | Dashboard seller | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/products` | Produk seller | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/products/new` | Tambah produk | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/products/create` | Simpan produk | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/orders` | Order seller | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/payouts` | Payout seller | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/payout/request` | Request payout | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/settings` | Setting toko | `unitrade_seller/controllers/main.py` |
| `/unitrade/seller/chat` | Chat seller | `unitrade_chat/controllers/main.py` |
| `/unitrade/seller/notifications` | Notifikasi seller | `unitrade_notification/controllers/main.py` |

### Admin

| URL/route | Fungsi | Lokasi |
| --- | --- | --- |
| `/unitrade/admin` | Dashboard admin | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/users` | User management | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/ktm-verifications` | KTM queue | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/products` | Product management | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/transactions` | Transaction management | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/payouts` | Payout management | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/refunds` | Refund/dispute | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/reviews` | Review moderation | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/customer-service` | Customer service admin | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/live-chat` | Live chat admin | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/settings` | Setting admin | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/audit-logs` | Audit log | `unitrade_admin/controllers/admin_dashboard.py` |

### API Penting

| Route | Function utama | Lokasi |
| --- | --- | --- |
| `/unitrade/payment/midtrans/webhook` | `midtrans_webhook` | `unitrade_payment/controllers/main.py` |
| `/unitrade/order/status/<order_id>/data` | `unitrade_order_status_data` | `unitrade_payment/controllers/main.py` |
| `/unitrade/order/<order_id>/confirm-received` | `unitrade_order_confirm_received` | `unitrade_payment/controllers/main.py` |
| `/seller/order/<ledger_id>/confirm-handoff` | `seller_order_confirm_handoff` | `unitrade_payment/controllers/main.py` |
| `/unitrade/chat/open` | `open_chat` | `unitrade_chat/controllers/main.py` |
| `/unitrade/chat/send` | `send_message` | `unitrade_chat/controllers/main.py` |
| `/unitrade/chat/presence` | `presence` | `unitrade_chat/controllers/main.py` |
| `/unitrade/reviews/create` | `create_review` | `unitrade_review/controllers/main.py` |
| `/unitrade/reviews/helpful/toggle` | `toggle_helpful` | `unitrade_review/controllers/main.py` |
| `/unitrade/reviews/report` | `report_review` | `unitrade_review/controllers/main.py` |
| `/unitrade/wishlist/toggle` | `wishlist_toggle` | `unitrade_wishlist/controllers/main.py` |
| `/unitrade/admin/api/verifications/approve` | `api_approve_verification` | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/api/verifications/reject` | `api_reject_verification` | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/api/sellers/revoke` | `api_revoke_seller` | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/api/payouts/action` | `api_payout_action` | `unitrade_admin/controllers/admin_dashboard.py` |
| `/unitrade/admin/api/refunds/action` | `api_refund_action` | `unitrade_admin/controllers/admin_dashboard.py` |

## Module dan Class Reference

### `unitrade_theme`

Peran: website utama, login/signup/OTP, profile, alamat, cart, checkout, customer service manual.

Model/class:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeOtp` / `unitrade.otp` | `models/otp.py` | Generate dan validasi OTP |
| `ResUsers` / inherit `res.users` | `models/res_users.py` | Field profile, notification email, security activity, online helper |
| `ResPartner` / inherit `res.partner` | `models/res_partner.py` | Field alamat tambahan |
| `SaleOrder` / inherit `sale.order` | `models/sale_order.py` | Validasi cart, stock warning, checkout state |
| `UnitradeCustomerTicket` | `models/customer_service.py` | Ticket customer service |
| `UnitradeSponsorshipRequest` | `models/sponsorship.py` | Request sponsorship |

Controller:

| Controller | File | Peran |
| --- | --- | --- |
| `UnitradeAuthController` | `controllers/controllers.py` | Login, signup, reset password, OTP email |
| `UnitradeOTPController` | `controllers/controllers.py` | Halaman dan submit OTP |
| `UnitradePortalProfile` | `controllers/controllers.py` | Profile, alamat, settings, pesanan |
| `UnitradeWebsiteSaleCart` | `controllers/cart.py` | Cart, update cart, stock validation |
| `UnitradeCheckout` | `controllers/checkout.py` | Checkout, voucher, shipping, payment |

Function penting:

| Function | Peran |
| --- | --- |
| `generate_otp`, `verify_otp` | Membuat dan validasi OTP |
| `web_login`, `web_auth_signup` | Login dan signup custom |
| `_generate_and_redirect_otp`, `verify_otp_submit` | Flow OTP |
| `account`, `save_unitrade_address` | Profile dan alamat |
| `_unitrade_validate_address_values` | Validasi alamat |
| `cart_update`, `cart_update_json` | Update cart |
| `_unitrade_product_stock_warning` | Cek stok |
| `checkout`, `unitrade_checkout_pay` | Checkout dan lanjut bayar |

### `unitrade_seller`

Peran: seller, verifikasi KTM, dashboard seller, produk seller, order seller, payout request.

Model/class:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeSeller` / `unitrade.seller` | `models/seller.py` | Data seller, status, payout account, revoke |
| `SellerVerification` / `unitrade.seller.verification` | `models/seller_verification.py` | Pengajuan KTM dan approval |
| `UnisaStudent` | `models/seller_verification.py` | Data mahasiswa pembanding |
| `UnitradeUniversity` | `models/university.py` | Master kampus |
| `ResUsersUniTrade` | `models/res_users.py` | Field status seller di user |

Function penting:

| Function | Peran |
| --- | --- |
| `seller_verification_submit` | Menerima upload KTM |
| `_check_upload_rate_limit` | Batas upload KTM |
| `action_submit_verification` | Mulai proses verifikasi |
| `_run_ocr_verification` | OCR KTM |
| `_prepare_seller_vals` | Menyiapkan data seller dari verification |
| `_approve_to_seller` | Membuat/update seller |
| `action_approve`, `action_reject` | Approve/reject KTM |
| `_unitrade_sync_user_seller_flags` | Sinkron status user-seller |
| `action_revoke_seller_verification` | Lepas status seller |
| `_unitrade_deactivate_marketplace_products` | Nonaktifkan produk seller setelah revoke |

### `unitrade_product_ext`

Peran: memperluas produk Odoo menjadi produk marketplace.

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `ProductTemplateUniTrade` | `models/product_template.py` | Field seller, kondisi, lokasi, listing status, fee status |
| `ProductProductUniTrade` | `models/product_template.py` | Sinkron variant |
| `ProductImageUniTrade` | `models/product_template.py` | Extension gambar |
| `UnitradeProductWaiveWizard` | `models/product_wizards.py` | Waive listing fee |
| `UnitradeProductRejectWizard` | `models/product_wizards.py` | Reject produk |

Field penting:

| Field | Fungsi |
| --- | --- |
| `x_seller_id` | Seller pemilik produk |
| `x_seller_user_id` | User seller |
| `x_condition` | Kondisi barang |
| `x_item_district`, `x_item_province` | Lokasi item |
| `x_listing_status` | Status listing |
| `x_listing_fee_status` | Status biaya listing |

### `unitrade_payment`

Peran: Midtrans, payment intent, payment event, escrow, order status, payout, voucher.

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradePaymentIntent` | `models/payment_intent.py` | Transaksi pembayaran |
| `UnitradePaymentEvent` | `models/payment_event.py` | Log webhook |
| `UnitradeEscrowLedger` | `models/escrow_ledger.py` | Dana seller ditahan/dilepas |
| `UnitradeSellerPayout` | `models/seller_payout.py` | Payout manual admin |
| `SaleOrderUniTrade` | `models/sale_order.py` | Field payment/order/escrow |
| `UnitradeVoucher` | `models/voucher.py` | Voucher |

Function penting:

| Function | Peran |
| --- | --- |
| `_midtrans_send_charge_request` | Kirim request charge ke Midtrans |
| `_validate_midtrans_signature` | Validasi webhook |
| `_normalize_midtrans_status` | Normalisasi status provider |
| `_find_midtrans_intent_from_payload` | Cari payment intent dari payload |
| `midtrans_webhook` | Endpoint webhook |
| `unitrade_order_status`, `_order_status_values` | Halaman status order |
| `_create_for_order`, `ensure_for_order` | Membuat escrow ledger |
| `action_seller_confirm_handoff` | Seller serahkan barang |
| `action_buyer_confirm_received` | Buyer terima barang |
| `_mark_releasable_if_fully_confirmed` | Dana siap payout |
| `create_payout_for_seller` | Membuat payout |
| `_validate_ledgers_for_payout` | Validasi ledger payout |
| `_reserve_ledgers` | Cegah double payout |
| `action_mark_paid` | Admin mark paid dan release ledger |

### `unitrade_delivery`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeDelivery` | `models/delivery.py` | Data pengiriman |
| `SaleOrderShipping` | `models/sale_order_shipping.py` | Field shipping method order |

Field penting: `order_id`, `seller_id`, `buyer_id`, `status`, `shipping_method`.

### `unitrade_dispute`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeDispute` | `models/dispute.py` | Kasus refund/dispute |
| `UnitradeDisputeEvidence` | `models/dispute.py` | Bukti dispute |
| `UnitradeDisputeTimeline` | `models/dispute.py` | Riwayat kasus |
| `SaleOrderUniTradeDispute` | `models/sale_order.py` | Refund state di order |
| `UnitradeEscrowLedgerDispute` | `models/escrow_ledger.py` | Relasi dispute ke escrow |

Route penting ada di `unitrade_dispute/controllers/main.py`: form refund, submit refund, detail refund, seller response.

### `unitrade_chat`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeChatConversation` | `models/chat.py` | Room chat buyer-seller |
| `UnitradeChatMessage` | `models/chat.py` | Pesan chat |
| `UnitradeChatReport` | `models/chat.py` | Laporan chat |
| `UnitradeChatRateLimit` | `models/chat.py` | Batas spam |
| `ResUsers` inherit | `models/res_users.py` | Presence/last seen |

Function penting:

| Function | Peran |
| --- | --- |
| `open_for_seller` | Ambil/buat conversation |
| `_canonical_for_pair` | Dedupe room |
| `_conversation_payload` | Data untuk frontend |
| `create_from_controller` | Buat message/report |
| `_notify`, `_notify_message` | Update realtime bus |
| `mark_read` | Tandai pesan dibaca |
| `_is_other_online` | Status online lawan chat |
| `check` | Rate limit |
| `open_chat`, `send_message`, `presence`, `report_user` | Endpoint chat |

### `unitrade_notification`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeNotification` | `models/notification.py` | Data notifikasi |
| `UnitradeNotificationPreference` | `models/notification_preference.py` | Preferensi notifikasi |
| `UnitradeAnnouncement` | `models/announcement.py` | Pengumuman |
| Payment/order/chat/review/seller hooks | `models/*_hooks.py` | Membuat notifikasi otomatis |

Function penting:

| Function | Peran |
| --- | --- |
| `emit` | Membuat notifikasi user |
| `broadcast` | Broadcast notifikasi |
| `_build_idempotency_key` | Cegah duplikat |
| `_validate_action_url` | Validasi URL target |
| `_get_effective_action_url` | URL final |
| `_buyer_notification_order_status_url` | URL status order buyer |
| `_is_buyer_shipped_order_notification` | Deteksi pesanan dikirim |
| `notification_center`, `seller_notification_center` | Halaman notifikasi |
| `mark_read`, `mark_all_read` | Tandai dibaca |

### `unitrade_review`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeReview` | `models/review.py` | Review produk |
| `UnitradeReviewHelpful` | `models/review.py` | Vote membantu |
| `UnitradeReviewReport` | `models/review.py` | Report ulasan |

Function penting:

| Function | Peran |
| --- | --- |
| `_eligible_order`, `_can_review` | Cek boleh review |
| `create_review` | Membuat review |
| `toggle_helpful` | Toggle helpful vote |
| `report_review` | Membuat report |
| `_compute_interaction_counts` | Hitung helpful/report |
| `_unitrade_refresh_product_review_stats` | Update rating produk |
| `_check_order_done` | Validasi order selesai |

### `unitrade_wishlist`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeWishlist` | `models/wishlist.py` | Relasi user-produk favorit |
| `UnitradeWishlistController` | `controllers/main.py` | Halaman, toggle, status, remove |

Function penting: `wishlist_page`, `wishlist_toggle`, `wishlist_status`, `wishlist_remove`, `_prepare_wishlist_groups`.

### `unitrade_cs_ai`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeCsSession` | `models/cs_session.py` | Session CS AI/live chat |
| `UnitradeCsSessionMessage` | `models/cs_session.py` | Pesan CS |
| `UnitradeCsAiService` | `models/cs_ai_service.py` | Service Gemini |
| `ChatRateLimitCsAi` | `models/chat_rate_limit.py` | Rate limit CS |
| `CustomerTicketCsAi` | `models/customer_ticket.py` | Relasi ticket-session |

Function penting:

| Function | Peran |
| --- | --- |
| `get_or_create_active` | Ambil/buat session |
| `_post_greeting` | Greeting AI |
| `post_user_message` | Simpan pesan user |
| `_maybe_generate_ai_reply` | Generate jawaban AI |
| `generate_reply` | Panggil Gemini |
| `escalate_to_admin` | Masuk queue admin |
| `_ensure_ticket` | Buat/hubungkan ticket |
| `admin_start_handling`, `admin_reply`, `close_session` | Flow admin CS |

### `unitrade_admin`

Class/model:

| Class/model | File | Fungsi |
| --- | --- | --- |
| `UnitradeAdminStats` | `models/admin_stats.py` | Aggregator data dan action admin |
| `UnitradeAdminAuditLog` | `models/audit_log.py` | Audit log |
| `SaleOrderUnitradeAdmin` | `models/sale_order.py` | Field/action admin order |
| `UnitradeAdminSettings` | `models/res_config_settings.py` | Setting admin |
| `UnitradeAdminController` | `controllers/admin_dashboard.py` | Route dashboard/API admin |

Function penting:

| Function | Peran |
| --- | --- |
| `get_dashboard_data` | Ringkasan dashboard |
| `get_ktm_verification_queue` | Queue KTM |
| `admin_approve_verification`, `admin_reject_verification` | Approve/reject KTM |
| `admin_revoke_seller` | Revoke seller |
| `get_products_page`, `admin_run_product_action` | Product admin |
| `get_payouts_page`, `admin_run_payout_action` | Payout admin |
| `get_refunds_page`, `admin_refund_action` | Refund admin |
| `get_reviews_page`, `admin_toggle_review_visibility` | Review moderation |
| `get_live_chat_sessions`, `get_live_chat_detail` | Live chat admin |
| `save_settings` | Simpan setting |
| `log_action` | Audit log |

## Function Map Per Fitur

### OTP

Urutan kode:

1. `web_auth_signup` atau `send_otp_to_email`
2. `generate_otp`
3. `_send_otp_email`
4. `verify_otp_page`
5. `verify_otp_submit`
6. `verify_otp`

Data: `res.users`, `unitrade.otp`, `unitrade.security.activity`.

### KTM Verification

Urutan kode:

1. `seller_verification_page`
2. `seller_verification_submit`
3. `_run_ocr_verification`
4. record `unitrade.seller.verification` dibuat/update
5. `get_ktm_verification_queue`
6. `admin_approve_verification` atau `admin_reject_verification`
7. `action_approve` / `action_reject`
8. `_approve_to_seller`
9. `_unitrade_sync_user_seller_flags`

Data: `unitrade.seller.verification`, `unitrade.seller`, `res.users`, `ir.attachment`.

### Payment dan Escrow

Urutan kode:

1. `unitrade_checkout_pay`
2. `unitrade.payment.intent` dibuat
3. `_midtrans_send_charge_request`
4. `midtrans_webhook`
5. `_validate_midtrans_signature`
6. `_normalize_midtrans_status`
7. `_find_midtrans_intent_from_payload`
8. payment intent/order update
9. `ensure_for_order`
10. `_create_for_order`

Data: `sale.order`, `unitrade.payment.intent`, `unitrade.payment.event`, `unitrade.escrow.ledger`.

### Payout

Urutan kode:

1. Seller save payout account.
2. Seller request payout.
3. `create_payout_for_seller`
4. `_eligible_ledgers_domain`
5. `_validate_ledgers_for_payout`
6. `_reserve_ledgers`
7. Admin membuka payout page.
8. `admin_run_payout_action`
9. `action_mark_paid`
10. Ledger menjadi released.

Data: `unitrade.seller`, `unitrade.seller.payout`, `unitrade.escrow.ledger`, `unitrade.admin.audit.log`.

### Chat

Urutan kode:

1. `open_chat`
2. `open_for_seller`
3. `_canonical_for_pair`
4. `bootstrap`
5. `send_message`
6. `UnitradeChatMessage.create_from_controller`
7. `_notify_message`
8. notification hook membuat notifikasi
9. `presence` update online status

Data: `unitrade.chat.conversation`, `unitrade.chat.message`, `unitrade.notification`, `res.users`.

### Notification

Urutan kode:

1. Event terjadi di payment/order/chat/review/seller.
2. Hook module terkait berjalan.
3. `emit` atau `broadcast`.
4. `_build_idempotency_key`.
5. `_get_effective_action_url`.
6. Navbar/notification center membaca data.
7. `mark_read` saat user membaca.

Data: `unitrade.notification`, `unitrade.notification.preference`, `unitrade.announcement`.

### Review

Urutan kode:

1. `review_status`
2. `_can_review`
3. `create_review`
4. `_check_order_done`
5. `_unitrade_refresh_product_review_stats`
6. `toggle_helpful` jika user vote
7. `report_review` jika user report
8. Admin moderation jika ada report

Data: `unitrade.review`, `unitrade.review.helpful`, `unitrade.review.report`, `product.template`.

### Customer Service AI

Urutan kode:

1. `cs_chat_session`
2. `get_or_create_active`
3. `_post_greeting`
4. `cs_chat_send`
5. `post_user_message`
6. `_maybe_generate_ai_reply`
7. `generate_reply`
8. `cs_chat_escalate`
9. `escalate_to_admin`
10. `admin_reply`
11. `close_session`

Data: `unitrade.cs.session`, `unitrade.cs.session.message`, `unitrade.customer.ticket`.

### Admin Action

Urutan kode umum:

1. Admin membuka route `/unitrade/admin/...`.
2. Controller cek `_is_admin`.
3. Controller memanggil `_stats()`.
4. `unitrade.admin.stats` membaca data.
5. API action memanggil method admin, misalnya `admin_approve_verification`.
6. Method admin memanggil model target.
7. Audit log dibuat.
8. Response JSON dikirim ke frontend.

Data: model target + `unitrade.admin.audit.log`.

## Cara Cepat Trace Bug

KTM pending tidak muncul:

1. Cek `unitrade.seller.verification`.
2. Cek `state`.
3. Cek `get_ktm_verification_queue`.
4. Cek domain/filter.
5. Cek group admin.

Notifikasi order salah redirect:

1. Cek `unitrade.notification`.
2. Cek payload/reference/action URL.
3. Cek `_is_buyer_shipped_order_notification`.
4. Cek `_buyer_notification_order_status_url`.
5. Pastikan URL ke `/unitrade/order/status/[order_id]`.

Dana tidak bisa payout:

1. Cek ledger `state`.
2. Cek `payout_status`.
3. Cek dispute aktif.
4. Cek rekening seller.
5. Cek `_validate_ledgers_for_payout`.
6. Cek audit log admin.
