# -*- coding: utf-8 -*-
"""Reset and seed fresh UniTrade marketplace test data.

Run this file through Odoo shell. It is dry-run by default.

Dry-run:
    odoo-bin shell -c <odoo.conf> -d <db_name> < scripts/seed_unitrade_test_data.py

Execute reset + seed:
    set UNITRADE_RESET_TEST_DATA=YES
    odoo-bin shell -c <odoo.conf> -d <db_name> < scripts/seed_unitrade_test_data.py

The reset intentionally targets UniTrade marketplace data and seed logins only.
It does not delete Odoo system products such as service/payment fee products.
"""

import base64
import binascii
import logging
import os
import struct
import zlib
from datetime import timedelta

from odoo import SUPERUSER_ID, fields

_logger = logging.getLogger(__name__)

MARKER = "UNITRADE_TEST_SEED"
EXECUTE = os.environ.get("UNITRADE_RESET_TEST_DATA") == "YES"
SEED_SAMPLE_TRANSACTIONS = os.environ.get("UNITRADE_SEED_SAMPLE_TRANSACTIONS", "YES") != "NO"
DEFAULT_PASSWORD = os.environ.get("UNITRADE_SEED_PASSWORD", "UnitradeTest123!")

DISTRICT_LABELS = {
    "yogyakarta": "Kota Yogyakarta",
    "sleman": "Sleman",
    "bantul": "Bantul",
    "kulon_progo": "Kulon Progo",
    "gunungkidul": "Gunungkidul",
}


def _env():
    try:
        return env  # noqa: F821 - provided by odoo-bin shell
    except NameError as exc:
        raise RuntimeError("Run this script with odoo-bin shell so the `env` variable exists.") from exc


ENV = _env()


def _model_exists(model_name):
    try:
        ENV[model_name]
        return True
    except KeyError:
        return False


def _model(model_name):
    if not _model_exists(model_name):
        return False
    return ENV[model_name].sudo()


def _log_action(message, *args):
    prefix = "[EXECUTE]" if EXECUTE else "[DRY-RUN]"
    _logger.info("%s %s", prefix, message % args if args else message)


def _force_attachment_storage_db():
    if not EXECUTE:
        return (False, False)
    Param = ENV["ir.config_parameter"].sudo()
    param = Param.search([("key", "=", "ir_attachment.location")], limit=1)
    previous = param.value if param else False
    had_param = bool(param)
    Param.set_param("ir_attachment.location", "db")
    _logger.info("Temporarily using database attachment storage for seed images.")
    return (had_param, previous)


def _restore_attachment_storage(previous_state):
    if not EXECUTE:
        return
    had_param, previous = previous_state
    Param = ENV["ir.config_parameter"].sudo()
    if had_param:
        Param.set_param("ir_attachment.location", previous or "file")
        _logger.info("Restored ir_attachment.location=%s", previous or "file")
        return
    Param.search([("key", "=", "ir_attachment.location")]).unlink()
    _logger.info("Removed temporary ir_attachment.location override.")


def _purge_attachments_for(model_name, res_ids, label):
    res_ids = [item for item in (res_ids or []) if item]
    if not res_ids:
        return 0
    Attachment = ENV["ir.attachment"].sudo()
    attachments = Attachment.search([
        ("res_model", "=", model_name),
        ("res_id", "in", res_ids),
    ])
    if not attachments:
        return 0
    count = len(attachments)
    if not EXECUTE:
        _log_action("Would SQL-purge %s attachment(s) for %s", count, label)
        return count
    ENV.cr.execute("DELETE FROM ir_attachment WHERE id = ANY(%s)", (attachments.ids,))
    _logger.info("SQL-purged %s attachment(s) for %s", count, label)
    return count


def _safe_unlink(records, label):
    records = records.exists()
    if not records:
        return 0
    count = len(records)
    if not EXECUTE:
        _log_action("Would unlink %s %s", count, label)
        return count
    try:
        with ENV.cr.savepoint():
            records.unlink()
        _logger.info("Unlinked %s %s", count, label)
        return count
    except Exception:
        _logger.exception("Batch unlink failed for %s %s; retrying one by one.", count, label)
        success_count = 0
        for record in records.exists():
            try:
                with ENV.cr.savepoint():
                    record.unlink()
                success_count += 1
            except Exception:
                _logger.exception("Failed to unlink %s id=%s", label, record.id)
        if success_count:
            _logger.info("Unlinked %s/%s %s after per-record retry.", success_count, count, label)
        return success_count


def _safe_write(records, values, label):
    records = records.exists()
    if not records:
        return 0
    count = len(records)
    if not EXECUTE:
        _log_action("Would write %s on %s %s", values, count, label)
        return count
    try:
        with ENV.cr.savepoint():
            records.write(values)
        _logger.info("Updated %s %s", count, label)
        return count
    except Exception:
        _logger.exception("Failed to update %s %s", count, label)
        return 0


def _png_base64(primary, secondary):
    """Generate a small valid PNG using only the Python standard library."""
    width = 256
    height = 256
    raw_rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            color = primary if ((x // 32) + (y // 32)) % 2 == 0 else secondary
            row.extend(color)
        raw_rows.append(bytes(row))
    raw = b"".join(raw_rows)

    def chunk(tag, data):
        crc = binascii.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png)


IMAGE_PALETTE = [
    ((255, 213, 79), (32, 38, 46)),
    ((191, 219, 254), (15, 23, 42)),
    ((187, 247, 208), (22, 101, 52)),
    ((253, 186, 116), (124, 45, 18)),
    ((221, 214, 254), (76, 29, 149)),
    ((254, 202, 202), (153, 27, 27)),
]


def _image(index):
    primary, secondary = IMAGE_PALETTE[index % len(IMAGE_PALETTE)]
    return _png_base64(primary, secondary)


def _profile_image(spec):
    seed = sum(ord(char) for char in spec.get("login", spec.get("name", "")))
    return _image(seed % len(IMAGE_PALETTE))


def _seed_logins():
    return [item["login"] for item in BUYERS + SELLERS]


def _record_by_xmlid(xmlid):
    return ENV.ref(xmlid, raise_if_not_found=False)


def _category(xmlid):
    category = _record_by_xmlid(xmlid)
    if category:
        return category
    return ENV["product.category"].sudo().search([], limit=1)


BUYERS = [
    {
        "name": "Fuad Adi Darmawan",
        "login": "unitrade.test.buyer.fuad@unitrade.test",
        "phone": "+62 812-1000-2001",
        "city": "Sleman",
        "street": "Jl. Ringroad Barat, Sleman",
    },
    {
        "name": "Maharani Dwi Rocky",
        "login": "unitrade.test.buyer.maharani@unitrade.test",
        "phone": "+62 812-1000-2002",
        "city": "Yogyakarta",
        "street": "Jl. Tamansiswa, Kota Yogyakarta",
    },
    {
        "name": "Salsabila Putri",
        "login": "unitrade.test.buyer.salsa@unitrade.test",
        "phone": "+62 812-1000-2003",
        "city": "Bantul",
        "street": "Jl. Bantul KM 7, Bantul",
    },
    {
        "name": "Andika Pratama",
        "login": "unitrade.test.buyer.andika@unitrade.test",
        "phone": "+62 812-1000-2004",
        "city": "Kulon Progo",
        "street": "Jl. Wates, Kulon Progo",
    },
]

SELLERS = [
    {
        "name": "Nur Pia Ramadhani",
        "login": "unitrade.test.seller.nurpia@unitrade.test",
        "nim": "24101010001",
        "faculty": "Fakultas Ilmu Kesehatan",
        "phone": "+62 812-2000-3001",
        "city": "Sleman",
        "street": "Jl. Ringroad Barat, Sleman",
        "slug": "nur-pia-store",
        "payout": ("ID_BCA", "1234567890", "Nur Pia Ramadhani"),
    },
    {
        "name": "Dwi Rezkya Desyafa",
        "login": "unitrade.test.seller.dwi@unitrade.test",
        "nim": "24101010002",
        "faculty": "Fakultas Ekonomi dan Sosial",
        "phone": "+62 812-2000-3002",
        "city": "Yogyakarta",
        "street": "Jl. Taman Siswa, Kota Yogyakarta",
        "slug": "dwi-campus-shop",
        "payout": ("ID_MANDIRI", "9876543210", "Dwi Rezkya Desyafa"),
    },
    {
        "name": "Rizky Aulia Putra",
        "login": "unitrade.test.seller.rizky@unitrade.test",
        "nim": "24101010003",
        "faculty": "Fakultas Sains dan Teknologi",
        "phone": "+62 812-2000-3003",
        "city": "Bantul",
        "street": "Jl. Bantul KM 8, Bantul",
        "slug": "rizky-tech-corner",
        "payout": (False, False, False),
    },
]

PRODUCTS = [
    {
        "code": "UT-SEED-HP-001",
        "name": "Headphone Sony WH-1000XM4",
        "seller": 0,
        "category": "unitrade_product_ext.product_category_unitrade_electronics",
        "price": 3200000,
        "stock": 4,
        "condition": "used",
        "district": "sleman",
        "brand": "Sony",
        "weight": 280,
        "description": "Headphone noise cancelling kondisi mulus, lengkap pouch dan kabel.",
    },
    {
        "code": "UT-SEED-KBD-002",
        "name": "Keyboard Mechanical RGB",
        "seller": 2,
        "category": "unitrade_product_ext.product_category_unitrade_electronics",
        "price": 450000,
        "stock": 6,
        "condition": "used",
        "district": "bantul",
        "brand": "Keychron",
        "weight": 850,
        "description": "Keyboard mechanical switch brown, RGB normal, cocok untuk tugas dan gaming.",
    },
    {
        "code": "UT-SEED-CAL-003",
        "name": "Kalkulator Scientific Casio",
        "seller": 1,
        "category": "unitrade_product_ext.product_category_unitrade_electronics",
        "price": 135000,
        "stock": 8,
        "condition": "used",
        "district": "yogyakarta",
        "brand": "Casio",
        "weight": 150,
        "description": "Kalkulator scientific untuk statistik dan matematika, tombol masih responsif.",
    },
    {
        "code": "UT-SEED-LAB-004",
        "name": "Jas Lab Putih Ukuran M",
        "seller": 0,
        "category": "unitrade_product_ext.product_category_unitrade_fashion",
        "price": 85000,
        "stock": 5,
        "condition": "used",
        "district": "sleman",
        "brand": "UniTrade",
        "weight": 300,
        "description": "Jas lab putih ukuran M, cocok untuk praktikum kesehatan.",
    },
    {
        "code": "UT-SEED-BUKU-005",
        "name": "Buku Keperawatan Dasar",
        "seller": 0,
        "category": "unitrade_product_ext.product_category_unitrade_other",
        "price": 65000,
        "stock": 10,
        "condition": "used",
        "district": "sleman",
        "brand": "Salemba",
        "weight": 500,
        "description": "Buku referensi keperawatan dasar, beberapa halaman diberi stabilo.",
    },
    {
        "code": "UT-SEED-LAMP-006",
        "name": "Lampu Meja Belajar LED",
        "seller": 1,
        "category": "unitrade_product_ext.product_category_unitrade_furniture",
        "price": 120000,
        "stock": 4,
        "condition": "new",
        "district": "yogyakarta",
        "brand": "Mijia",
        "weight": 700,
        "description": "Lampu meja LED tiga mode cahaya, hemat listrik untuk belajar malam.",
    },
    {
        "code": "UT-SEED-TOTE-007",
        "name": "Tote Bag Kanvas UniTrade",
        "seller": 1,
        "category": "unitrade_product_ext.product_category_unitrade_fashion",
        "price": 55000,
        "stock": 12,
        "condition": "new",
        "district": "yogyakarta",
        "brand": "Local Craft",
        "weight": 180,
        "description": "Tote bag kanvas tebal untuk buku kuliah dan laptop kecil.",
    },
    {
        "code": "UT-SEED-SKIN-008",
        "name": "Skincare Travel Kit",
        "seller": 0,
        "category": "unitrade_product_ext.product_category_unitrade_health_beauty",
        "price": 75000,
        "stock": 9,
        "condition": "new",
        "district": "sleman",
        "brand": "Wardah",
        "weight": 250,
        "description": "Paket skincare travel size sealed, cocok untuk kegiatan kampus.",
    },
    {
        "code": "UT-SEED-SNACK-009",
        "name": "Paket Snack Kelas",
        "seller": 1,
        "category": "unitrade_product_ext.product_category_unitrade_food",
        "price": 25000,
        "stock": 30,
        "condition": "new",
        "district": "yogyakarta",
        "brand": "Dapur Kampus",
        "weight": 300,
        "description": "Paket snack isi 5 untuk rapat kelas atau kegiatan organisasi.",
    },
    {
        "code": "UT-SEED-CHAIR-010",
        "name": "Kursi Lipat Belajar",
        "seller": 2,
        "category": "unitrade_product_ext.product_category_unitrade_furniture",
        "price": 185000,
        "stock": 3,
        "condition": "used",
        "district": "bantul",
        "brand": "IKEA",
        "weight": 2500,
        "description": "Kursi lipat ringan untuk kos, rangka kokoh dan mudah disimpan.",
    },
    {
        "code": "UT-SEED-DESIGN-011",
        "name": "Jasa Desain Poster Kegiatan",
        "seller": 2,
        "category": "unitrade_product_ext.product_category_unitrade_services",
        "price": 50000,
        "stock": 20,
        "condition": "new",
        "district": "bantul",
        "brand": "Rizky Studio",
        "weight": 0,
        "description": "Jasa desain poster kegiatan kampus, termasuk dua kali revisi.",
    },
    {
        "code": "UT-SEED-MOUSE-012",
        "name": "Mouse Wireless Logitech",
        "seller": 2,
        "category": "unitrade_product_ext.product_category_unitrade_electronics",
        "price": 110000,
        "stock": 7,
        "condition": "used",
        "district": "bantul",
        "brand": "Logitech",
        "weight": 120,
        "description": "Mouse wireless hemat baterai, cocok untuk laptop kuliah.",
    },
]

REVIEW_COMMENTS = [
    "Produk sesuai deskripsi dan nyaman dipakai untuk kegiatan kampus.",
    "Kondisi barang bagus, seller responsif, dan transaksi lancar.",
    "Harga sepadan dengan kualitas. Cocok untuk kebutuhan mahasiswa.",
    "Barang diterima dengan baik dan detailnya sesuai foto produk.",
    "Pengalaman belanja aman, komunikasi dengan seller jelas.",
]


def _seed_user(spec):
    Users = ENV["res.users"].with_context(active_test=False, no_reset_password=True).sudo()
    Partner = ENV["res.partner"].with_context(active_test=False).sudo()
    portal_group = ENV.ref("base.group_portal", raise_if_not_found=False)
    partner_values = {
        "name": spec["name"],
        "email": spec["login"],
        "phone": spec.get("phone"),
        "mobile": spec.get("phone"),
        "city": spec.get("city"),
        "street": spec.get("street"),
        "comment": MARKER,
        "image_1920": _profile_image(spec),
        "active": True,
    }
    user = Users.search([("login", "=", spec["login"])], limit=1)
    if user:
        partner = user.partner_id
        partner.write(partner_values)
        values = {
            "name": spec["name"],
            "login": spec["login"],
            "email": spec["login"],
            "active": True,
            "password": DEFAULT_PASSWORD,
        }
        if portal_group:
            values["groups_id"] = [(6, 0, [portal_group.id])]
        if "is_otp_verified" in Users._fields:
            values["is_otp_verified"] = True
        if "x_is_email_verified" in Users._fields:
            values["x_is_email_verified"] = True
        if "image_1920" in Users._fields:
            values["image_1920"] = _profile_image(spec)
        user.write(values)
        return user

    partner = Partner.create(partner_values)
    values = {
        "name": spec["name"],
        "login": spec["login"],
        "email": spec["login"],
        "partner_id": partner.id,
        "password": DEFAULT_PASSWORD,
        "active": True,
    }
    if portal_group:
        values["groups_id"] = [(6, 0, [portal_group.id])]
    if "is_otp_verified" in Users._fields:
        values["is_otp_verified"] = True
    if "x_is_email_verified" in Users._fields:
        values["x_is_email_verified"] = True
    if "image_1920" in Users._fields:
        values["image_1920"] = _profile_image(spec)
    return Users.create(values)


def _seed_seller(spec):
    user = _seed_user(spec)
    Student = ENV["unisa.student"].with_context(active_test=False).sudo()
    Seller = ENV["unitrade.seller"].with_context(active_test=False).sudo()
    student = Student.search([("nim", "=", spec["nim"])], limit=1)
    student_values = {
        "nim": spec["nim"],
        "name": spec["name"],
        "faculty": spec["faculty"],
        "active": True,
    }
    if student:
        student.write(student_values)
    else:
        Student.create(student_values)

    channel, account_number, account_name = spec.get("payout") or (False, False, False)
    seller_values = {
        "user_id": user.id,
        "nim": spec["nim"],
        "status": "verified",
        "verified_date": fields.Datetime.now(),
        "verified_by": SUPERUSER_ID,
        "x_store_slug": spec["slug"],
        "x_store_active": True,
        "x_chat_enabled": True,
        "x_store_province": "DI Yogyakarta",
        "x_store_city": spec["city"],
        "x_store_address_detail": spec.get("street") or "Area kampus UNISA Yogyakarta",
        "x_profile_address": "%s, DI Yogyakarta" % (spec.get("street") or spec["city"]),
        "x_profile_description": "Mahasiswa UNISA Yogyakarta, akun seed untuk testing UniTrade.",
        "x_payout_channel_code": channel,
        "x_payout_account_number": account_number,
        "x_payout_account_name": account_name,
        "ktm_image": _profile_image(spec),
        "ktm_filename": "ktm-%s.png" % spec["nim"],
        "ocr_result": "Seed OCR: %s / %s" % (spec["nim"], spec["name"]),
        "ocr_confidence": 99.0,
        "ocr_nim_match": True,
        "ocr_name_match": True,
        "ocr_student_name": spec["name"],
        "ocr_name_match_token": spec["name"].split()[0].lower(),
    }
    seller = Seller.search([("user_id", "=", user.id)], limit=1)
    if seller:
        seller.write(seller_values)
    else:
        seller = Seller.create(seller_values)
    user.write({"x_is_seller": True, "x_seller_id": seller.id})
    Verification = _model("unitrade.seller.verification")
    if Verification is not False:
        verification = Verification.search([("partner_id", "=", user.partner_id.id)], limit=1)
        verification_values = {
            "partner_id": user.partner_id.id,
            "ktm_image": _profile_image(spec),
            "ktm_filename": "ktm-%s.png" % spec["nim"],
            "nim_extracted": spec["nim"],
            "nim_valid": True,
            "nim_registered": True,
            "name_confidence": 0.99,
            "student_name": spec["name"],
            "name_match_token": spec["name"].split()[0].lower(),
            "confidence_flag": "high",
            "state": "approved",
            "reviewed_by": SUPERUSER_ID,
            "reviewed_date": fields.Datetime.now(),
            "review_note": "Seed verification approved for UniTrade testing.",
        }
        if verification:
            verification.write(verification_values)
        else:
            Verification.create(verification_values)
    return seller


def _seed_product(spec, sellers, image_index):
    Product = ENV["product.template"].with_context(
        active_test=False,
        unitrade_skip_marketplace_validation=True,
        tracking_disable=True,
    ).sudo()
    seller = sellers[spec["seller"]]
    district = spec["district"]
    product = Product.search([("default_code", "=", spec["code"])], limit=1)
    listing_start = fields.Datetime.now() - timedelta(days=image_index % 7)
    values = {
        "name": spec["name"],
        "default_code": spec["code"],
        "categ_id": _category(spec["category"]).id,
        "list_price": spec["price"],
        "standard_price": round(spec["price"] * 0.65, 2),
        "description_sale": spec["description"],
        "sale_ok": True,
        "purchase_ok": False,
        "website_published": True,
        "x_is_marketplace": True,
        "x_seller_id": seller.id,
        "x_seller_location": "%s, DI Yogyakarta" % DISTRICT_LABELS.get(district, seller.x_store_city),
        "x_item_province": "diy",
        "x_item_district": district,
        "x_condition": spec["condition"],
        "x_brand": spec["brand"],
        "x_weight_product": spec["weight"],
        "x_listing_fee": 10000,
        "x_listing_activated_at": listing_start,
        "x_listing_expires_at": listing_start + timedelta(days=30),
        "x_free_shipping": image_index % 4 == 0,
        "x_discount_percent": 5 if image_index % 5 == 0 else 0,
        "image_1920": _image(image_index),
        "x_specification": "<p>%s</p><ul><li>Kondisi: %s</li><li>Area: %s</li></ul>"
        % (spec["description"], "Baru" if spec["condition"] == "new" else "Bekas", DISTRICT_LABELS.get(district)),
    }
    if "detailed_type" in Product._fields:
        values["detailed_type"] = "product"
    elif "type" in Product._fields:
        values["type"] = "product"
    if "allow_out_of_stock_order" in Product._fields:
        values["allow_out_of_stock_order"] = False

    gallery_image = _image(image_index + 1)
    if product:
        product.write(values)
        if product.product_template_image_ids:
            product.product_template_image_ids.unlink()
        ENV["product.image"].with_context(unitrade_skip_marketplace_validation=True).sudo().create({
            "name": "%s - preview" % spec["name"],
            "product_tmpl_id": product.id,
            "image_1920": gallery_image,
        })
    else:
        values["product_template_image_ids"] = [(0, 0, {
            "name": "%s - preview" % spec["name"],
            "image_1920": gallery_image,
        })]
        product = Product.create(values)

    try:
        product.with_context(unitrade_skip_marketplace_validation=True).write({
            "x_unitrade_stock_qty": spec["stock"],
        })
    except Exception:
        _logger.exception("Failed to update stock quant for product %s; using manual stock fallback.", product.default_code)
        product.with_context(skip_unitrade_stock_inverse=True).write({
            "x_unitrade_manual_stock_qty": spec["stock"],
        })
    _seed_listing_fee_payment(product, seller, values["x_listing_fee"], listing_start)
    return product


def _seed_listing_fee_payment(product, seller, amount, paid_at):
    Intent = _model("unitrade.payment.intent")
    if Intent is False:
        if hasattr(product, "_unitrade_apply_listing_payment"):
            product._unitrade_apply_listing_payment(listing_fee=amount, paid_at=paid_at)
        else:
            product.write({
                "sale_ok": True,
                "website_published": True,
                "x_listing_activated_at": paid_at,
                "x_listing_expires_at": paid_at + timedelta(days=30),
            })
        return False

    name = "UT-SEED-LISTING-%s" % product.default_code
    intent = Intent.search([("name", "=", name)], limit=1)
    values = {
        "name": name,
        "provider": "midtrans",
        "intent_type": "listing_fee",
        "state": "paid",
        "amount": amount,
        "currency_id": product.currency_id.id,
        "product_template_id": product.id,
        "seller_id": seller.id,
        "partner_id": seller.partner_id.id,
        "payment_method_code": "gopay",
        "payment_method_label": "E-Wallet - GoPay",
        "payment_reference": name,
        "paid_at": paid_at,
    }
    if intent:
        intent.write(values)
    else:
        intent = Intent.create(values)
    if hasattr(product, "_unitrade_apply_listing_payment"):
        product._unitrade_apply_listing_payment(listing_fee=amount, paid_at=paid_at)
    return intent


def _create_payment_intent(order, seller, buyer):
    Intent = _model("unitrade.payment.intent")
    if Intent is False:
        return False
    name = "%s-SEED-INTENT" % order.name
    intent = Intent.search([("name", "=", name)], limit=1)
    values = {
        "name": name,
        "provider": "midtrans",
        "intent_type": "order_checkout",
        "state": "paid",
        "amount": order.amount_total,
        "currency_id": order.currency_id.id,
        "sale_order_id": order.id,
        "partner_id": buyer.partner_id.id,
        "seller_id": seller.id,
        "payment_method_code": "gopay",
        "payment_method_label": "E-Wallet - GoPay",
        "payment_reference": name,
        "paid_at": order.date_order,
    }
    if intent:
        intent.write(values)
    else:
        intent = Intent.create(values)
    order.write({
        "x_payment_intent_id": intent.id,
        "x_payment_provider": "midtrans",
        "x_payment_status": "paid",
        "x_payment_method": "E-Wallet - GoPay",
        "x_paid_at": order.date_order,
    })
    return intent


def _create_ledger(order, intent, seller, buyer, state="held", seller_confirmed=False, buyer_confirmed=False):
    Ledger = _model("unitrade.escrow.ledger")
    if Ledger is False:
        return False
    ledger = Ledger.search([("order_id", "=", order.id), ("seller_id", "=", seller.id)], limit=1)
    amount_seller = sum(
        line.price_subtotal
        for line in order.order_line
        if line.product_id and line.product_id.product_tmpl_id.x_seller_id.id == seller.id
    )
    now = fields.Datetime.now()
    values = {
        "name": "%s / %s" % (order.name, seller.name),
        "order_id": order.id,
        "payment_intent_id": intent.id if intent else False,
        "seller_id": seller.id,
        "buyer_id": buyer.partner_id.id,
        "currency_id": order.currency_id.id,
        "amount_total": order.amount_total,
        "amount_platform_fee": max(order.amount_total - amount_seller, 0.0),
        "amount_gateway_fee": 0.0,
        "amount_seller": amount_seller,
        "state": state,
        "seller_confirmed_at": now - timedelta(hours=4) if seller_confirmed else False,
        "buyer_confirmed_at": now - timedelta(hours=1) if buyer_confirmed else False,
        "completed_at": now - timedelta(hours=1) if seller_confirmed and buyer_confirmed else False,
        "seller_handoff_image": _image(10) if seller_confirmed else False,
        "seller_handoff_filename": "handoff-proof.png" if seller_confirmed else False,
        "seller_handoff_location": "Kampus UNISA Yogyakarta" if seller_confirmed else False,
        "buyer_received_image": _image(11) if buyer_confirmed else False,
        "buyer_received_filename": "received-proof.png" if buyer_confirmed else False,
    }
    if ledger:
        ledger.write(values)
    else:
        ledger = Ledger.create(values)
    ledger._sync_order_escrow_state()
    return ledger


def _seed_order(name_hint, buyer, product, qty, status_key, date_offset_days):
    SaleOrder = ENV["sale.order"].sudo()
    seller = product.x_seller_id
    date_order = fields.Datetime.now() - timedelta(days=date_offset_days)
    order = SaleOrder.create({
        "partner_id": buyer.partner_id.id,
        "date_order": date_order,
        "client_order_ref": "%s %s" % (MARKER, name_hint),
        "order_line": [(0, 0, {
            "product_id": product.product_variant_id.id,
            "product_uom_qty": qty,
            "price_unit": product.list_price,
            "tax_id": [(6, 0, [])],
        })],
    })
    try:
        order.action_confirm()
    except Exception:
        _logger.exception("Failed to confirm seed order %s; keeping it as sale test order.", order.name)
        order.write({"state": "sale"})

    intent = _create_payment_intent(order, seller, buyer)
    ledger_state = "held"
    seller_confirmed = False
    buyer_confirmed = False
    order_values = {
        "x_payment_status": "paid",
        "x_unitrade_order_state": "processing",
        "x_escrow_state": "held",
        "x_paid_at": date_order,
    }
    if status_key == "confirmation":
        seller_confirmed = True
    elif status_key == "completed":
        seller_confirmed = True
        buyer_confirmed = True
        ledger_state = "releasable"
        order_values.update({
            "x_unitrade_order_state": "completed",
            "x_completed_at": date_order + timedelta(hours=8),
        })
    elif status_key == "cancelled":
        ledger_state = "cancelled"
        order_values.update({
            "x_payment_status": "cancelled",
            "x_unitrade_order_state": "cancelled",
            "x_escrow_state": "cancelled",
            "x_cancelled_at": date_order + timedelta(hours=1),
            "x_cancel_reason": "Seed cancelled order",
        })
        try:
            order.action_cancel()
        except Exception:
            _logger.exception("Failed to cancel seed order %s", order.name)
    elif status_key == "refund":
        ledger_state = "disputed"
        order_values.update({
            "x_unitrade_order_state": "processing",
            "x_escrow_state": "disputed",
            "x_refund_state": "need_seller_response",
        })
    order.write(order_values)
    ledger = _create_ledger(order, intent, seller, buyer, ledger_state, seller_confirmed, buyer_confirmed)
    return order, ledger


def _seed_review_order(buyer, product, review_index):
    SaleOrder = ENV["sale.order"].with_context(
        tracking_disable=True,
        mail_create_nolog=True,
        mail_notrack=True,
        mail_notify_force_send=False,
    ).sudo()
    date_order = fields.Datetime.now() - timedelta(days=review_index + 7)
    order = SaleOrder.create({
        "partner_id": buyer.partner_id.id,
        "date_order": date_order,
        "client_order_ref": "%s REVIEW %s %s" % (MARKER, product.default_code, review_index + 1),
        "order_line": [(0, 0, {
            "product_id": product.product_variant_id.id,
            "product_uom_qty": 1,
            "price_unit": product.list_price,
            "tax_id": [(6, 0, [])],
        })],
    })
    order.write({
        "state": "sale",
        "x_payment_status": "paid",
        "x_unitrade_order_state": "completed",
        "x_escrow_state": "released",
        "x_paid_at": date_order,
        "x_completed_at": date_order + timedelta(hours=2),
    })
    return order


def _seed_refund(order, ledger, buyer, product):
    Dispute = _model("unitrade.dispute")
    if Dispute is False:
        return False
    existing = Dispute.search([("order_id", "=", order.id)], limit=1)
    line = order.order_line.filtered(lambda item: item.product_id.product_tmpl_id.id == product.id)[:1]
    values = {
        "state": "need_seller_response",
        "order_id": order.id,
        "order_line_id": line.id if line else False,
        "payment_intent_id": order.x_payment_intent_id.id if order.x_payment_intent_id else False,
        "escrow_ledger_id": ledger.id if ledger else False,
        "buyer_id": buyer.partner_id.id,
        "seller_id": product.x_seller_id.id,
        "reason_code": "damaged",
        "reason_note": "Produk tidak berfungsi normal setelah dicoba untuk kegiatan kuliah.",
        "requested_amount": line.price_subtotal if line else product.list_price,
        "refund_admin_fee_amount": 5000,
        "currency_id": order.currency_id.id,
        "submitted_at": fields.Datetime.now() - timedelta(hours=5),
    }
    if existing:
        existing.write(values)
        dispute = existing
    else:
        dispute = Dispute.create(values)
    for key, status in [
        ("order_created", "done"),
        ("payment_received", "done"),
        ("seller_handoff", "done"),
        ("buyer_received", "done"),
        ("return_requested", "done"),
        ("seller_review", "current"),
        ("refund_completed", "pending"),
    ]:
        dispute._record_timeline_event(key, status=status)
    Attachment = ENV["ir.attachment"].sudo()
    attachment = Attachment.create({
        "name": "refund-buyer-proof.png",
        "type": "binary",
        "datas": _image(12),
        "mimetype": "image/png",
        "res_model": "unitrade.dispute",
        "res_id": dispute.id,
    })
    Evidence = _model("unitrade.dispute.evidence")
    Evidence.search([("dispute_id", "=", dispute.id)]).unlink()
    Evidence.create({
        "dispute_id": dispute.id,
        "submitted_by_id": buyer.id,
        "evidence_type": "buyer_photo",
        "attachment_id": attachment.id,
        "note": "Bukti kondisi produk saat diterima.",
    })
    return dispute


def _seed_chat(buyer, seller, product, body):
    Conversation = _model("unitrade.chat.conversation")
    Message = _model("unitrade.chat.message")
    if Conversation is False or Message is False:
        return False
    conversation = Conversation.search([
        ("buyer_user_id", "=", buyer.id),
        ("seller_id", "=", seller.id),
        ("active", "=", True),
    ], limit=1)
    if not conversation:
        conversation = Conversation.create({
            "buyer_user_id": buyer.id,
            "seller_id": seller.id,
            "product_id": product.id,
        })
    Message.create({
        "conversation_id": conversation.id,
        "author_user_id": buyer.id,
        "message_type": "text",
        "body": body,
        "product_id": product.id,
    })
    Message.create({
        "conversation_id": conversation.id,
        "author_user_id": seller.user_id.id,
        "message_type": "text",
        "body": "Bisa, produk masih tersedia. Silakan checkout melalui UniTrade.",
        "product_id": product.id,
    })
    return conversation


def _seed_ticket(buyer, category, title, description, order=False):
    Ticket = _model("unitrade.customer.ticket")
    if Ticket is False:
        return False
    return Ticket.create({
        "user_id": buyer.id,
        "partner_id": buyer.partner_id.id,
        "category": category,
        "order_id": order.id if order else False,
        "title": title,
        "description": description,
        "status": "pending" if category != "contact_cs" else "in_progress",
    })


def _seed_review(buyer, order, product, rating, comment):
    Review = _model("unitrade.review")
    if Review is False:
        return False
    existing = Review.search([
        ("user_id", "=", buyer.id),
        ("order_id", "=", order.id),
        ("product_id", "=", product.id),
    ], limit=1)
    values = {
        "user_id": buyer.id,
        "order_id": order.id,
        "product_id": product.id,
        "rating": rating,
        "comment": comment,
        "is_visible": True,
    }
    if existing:
        existing.write(values)
        return existing
    return Review.create(values)


def _seed_product_reviews(buyers, products):
    for product_index, product in enumerate(products):
        for review_index, comment in enumerate(REVIEW_COMMENTS):
            buyer = buyers[(product_index + review_index) % len(buyers)]
            order = _seed_review_order(buyer, product, review_index)
            _seed_review(buyer, order, product, 5, comment)


def cleanup_existing_data():
    Users = ENV["res.users"].with_context(active_test=False).sudo()
    Partners = ENV["res.partner"].with_context(active_test=False).sudo()
    Products = ENV["product.template"].with_context(active_test=False).sudo()
    ProductImages = ENV["product.image"].with_context(active_test=False).sudo()
    seed_users = Users.search([("login", "in", _seed_logins())])
    seed_partners = seed_users.mapped("partner_id") | Partners.search([("comment", "ilike", MARKER)])
    marketplace_products = Products.search([
        "|",
        ("x_is_marketplace", "=", True),
        ("default_code", "ilike", "UT-SEED-"),
    ])
    variants = marketplace_products.mapped("product_variant_ids")
    sellers = ENV["unitrade.seller"].with_context(active_test=False).sudo().search([
        "|",
        ("user_id", "in", seed_users.ids),
        ("nim", "in", [item["nim"] for item in SELLERS]),
    ])

    orders = ENV["sale.order"].sudo().browse()
    if variants:
        orders |= ENV["sale.order.line"].sudo().search([("product_id", "in", variants.ids)]).mapped("order_id")
    if seed_partners:
        orders |= ENV["sale.order"].sudo().search([
            "|",
            ("partner_id", "in", seed_partners.ids),
            ("client_order_ref", "ilike", MARKER),
        ])

    if EXECUTE:
        product_images = ProductImages.search([("product_tmpl_id", "in", marketplace_products.ids)])
        Verification = _model("unitrade.seller.verification")
        verifications_for_purge = (
            Verification.search([("partner_id", "in", seed_partners.ids)])
            if Verification is not False and seed_partners
            else ENV["res.partner"].browse()
        )
        _purge_attachments_for("res.partner", seed_partners.ids, "seed partners/users")
        _purge_attachments_for("res.users", seed_users.ids, "seed users")
        _purge_attachments_for("unitrade.seller", sellers.ids, "seed sellers")
        _purge_attachments_for("unitrade.seller.verification", verifications_for_purge.ids, "seed seller verifications")
        _purge_attachments_for("product.template", marketplace_products.ids, "seed marketplace products")
        _purge_attachments_for("product.image", product_images.ids, "seed product gallery images")
        _purge_attachments_for("sale.order", orders.ids, "seed sale orders")

    disputes = _model("unitrade.dispute")
    if disputes is not False:
        dispute_records = disputes.search([
            "|",
            ("order_id", "in", orders.ids),
            ("seller_id", "in", marketplace_products.mapped("x_seller_id").ids),
        ]) if orders or marketplace_products else disputes.browse()
        _safe_unlink(_model("unitrade.dispute.timeline").search([("dispute_id", "in", dispute_records.ids)]), "dispute timelines")
        _safe_unlink(_model("unitrade.dispute.evidence").search([("dispute_id", "in", dispute_records.ids)]), "dispute evidence")
        _safe_unlink(dispute_records, "refund disputes")

    tickets = _model("unitrade.customer.ticket")
    if tickets is not False and seed_users:
        _safe_unlink(tickets.search([("user_id", "in", seed_users.ids)]), "customer service tickets")

    conversations = _model("unitrade.chat.conversation")
    if conversations is not False:
        chat_domain = []
        if seed_users:
            chat_domain = ["|", ("buyer_user_id", "in", seed_users.ids), ("seller_user_id", "in", seed_users.ids)]
        if marketplace_products:
            product_domain = [("product_id", "in", marketplace_products.ids)]
            chat_domain = ["|"] + chat_domain + product_domain if chat_domain else product_domain
        if chat_domain:
            _safe_unlink(conversations.search(chat_domain), "chat conversations")

    review = _model("unitrade.review")
    if review is not False and marketplace_products:
        _safe_unlink(review.search([("product_id", "in", marketplace_products.ids)]), "product reviews")

    ledger = _model("unitrade.escrow.ledger")
    if ledger is not False and orders:
        _safe_unlink(ledger.search([("order_id", "in", orders.ids)]), "escrow ledgers")

    intent = _model("unitrade.payment.intent")
    if intent is not False and (orders or marketplace_products):
        intent_domain = []
        if orders:
            intent_domain = [("sale_order_id", "in", orders.ids)]
        if marketplace_products:
            product_domain = [("product_template_id", "in", marketplace_products.ids)]
            intent_domain = ["|"] + intent_domain + product_domain if intent_domain else product_domain
        _safe_unlink(intent.search(intent_domain), "payment intents")

    if orders:
        if EXECUTE:
            for order in orders.exists():
                if order.state not in ("draft", "cancel"):
                    try:
                        with ENV.cr.savepoint():
                            order.action_cancel()
                    except Exception:
                        _logger.exception("Failed to cancel order %s before cleanup", order.name)
        _safe_unlink(orders, "sale orders")
        remaining_orders = orders.exists()
        if remaining_orders and EXECUTE:
            values = {
                "client_order_ref": "ARCHIVED_TEST_DATA",
                "x_payment_status": "cancelled",
                "x_unitrade_order_state": "cancelled",
                "x_escrow_state": "cancelled",
            }
            _safe_write(remaining_orders, values, "old seed sale orders that could not be deleted")

    if marketplace_products:
        _safe_unlink(ProductImages.search([("product_tmpl_id", "in", marketplace_products.ids)]), "product gallery images")
        deleted = _safe_unlink(marketplace_products, "marketplace product templates")
        remaining = marketplace_products.exists()
        if remaining and EXECUTE:
            _safe_write(remaining, {
                "active": False,
                "sale_ok": False,
                "website_published": False,
                "x_is_marketplace": False,
                "x_seller_id": False,
                "default_code": False,
            }, "marketplace products that could not be deleted")

    _safe_unlink(sellers, "seed seller profiles")
    verifications = _model("unitrade.seller.verification")
    if verifications is not False and seed_partners:
        _safe_unlink(verifications.search([("partner_id", "in", seed_partners.ids)]), "seller verification records")

    if seed_users:
        _safe_write(seed_users, {"active": False}, "old seed users")
    _log_action(
        "Cleanup scope: %s marketplace product(s), %s sale order(s), %s seed user(s)",
        len(marketplace_products),
        len(orders),
        len(seed_users),
    )


def seed_fresh_data():
    if not EXECUTE:
        _log_action(
            "Would create/update %s buyer(s), %s seller(s), %s product(s). Password: %s",
            len(BUYERS),
            len(SELLERS),
            len(PRODUCTS),
            DEFAULT_PASSWORD,
        )
        if SEED_SAMPLE_TRANSACTIONS:
            _log_action("Would create sample orders, one refund dispute, chats, tickets, and reviews.")
        return

    buyers = [_seed_user(item) for item in BUYERS]
    sellers = [_seed_seller(item) for item in SELLERS]
    products = [_seed_product(item, sellers, index) for index, item in enumerate(PRODUCTS)]

    if SEED_SAMPLE_TRANSACTIONS:
        order_processing, ledger_processing = _seed_order("processing", buyers[0], products[0], 1, "processing", 1)
        order_cancelled, _ledger_cancelled = _seed_order("cancelled", buyers[1], products[1], 1, "cancelled", 2)
        order_completed, _ledger_completed = _seed_order("completed", buyers[2], products[5], 1, "completed", 4)
        order_confirmation, _ledger_confirmation = _seed_order("confirmation", buyers[3], products[2], 2, "confirmation", 0)
        order_refund, ledger_refund = _seed_order("refund", buyers[0], products[3], 1, "refund", 3)
        _seed_refund(order_refund, ledger_refund, buyers[0], products[3])
        _seed_chat(buyers[0], sellers[0], products[0], "Headphone ini masih bisa nego?")
        _seed_chat(buyers[2], sellers[1], products[5], "Lampu meja bisa COD di kampus?")
        _seed_ticket(buyers[0], "refund_return", "Refund untuk jas lab", "Saya ingin cek proses pengembalian jas lab.", order_refund)
        _seed_ticket(buyers[1], "order_issue", "Pesanan dibatalkan", "Saya ingin memastikan dana pesanan yang dibatalkan aman.", order_cancelled)
        _seed_ticket(buyers[3], "contact_cs", "Butuh bantuan akun", "Saya ingin bertanya tentang perubahan nomor WhatsApp.")
        _seed_product_reviews(buyers, products)

    ENV.cr.commit()
    _logger.info("UniTrade seed completed. Test password for all seed users: %s", DEFAULT_PASSWORD)


attachment_storage_state = _force_attachment_storage_db()
try:
    cleanup_existing_data()
    seed_fresh_data()
finally:
    _restore_attachment_storage(attachment_storage_state)
