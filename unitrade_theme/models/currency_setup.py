"""Pastikan mata uang sistem UniTrade memakai Rupiah (IDR), bukan USD default.

Dipanggil dari data file via <function> sehingga jalan setiap kali modul
di-install maupun di-upgrade. Idempoten dan aman.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResCompanyUnitradeCurrency(models.Model):
    _inherit = 'res.company'

    @api.model
    def _unitrade_enforce_idr_currency(self):
        env = self.env
        idr = env.ref('base.IDR', raise_if_not_found=False)
        if not idr:
            _logger.warning('UniTrade: currency IDR tidak ditemukan, lewati setup currency.')
            return

        if not idr.active:
            idr.sudo().write({'active': True})

        # 1) Company currency -> IDR (hanya bila belum ada jurnal akuntansi)
        has_move_line = 'account.move.line' in env
        for company in env['res.company'].sudo().search([]):
            if company.currency_id == idr:
                continue
            has_moves = env['account.move.line'].sudo().search_count([
                ('company_id', '=', company.id),
            ]) if has_move_line else 0
            if has_moves:
                _logger.warning(
                    'UniTrade: company %s sudah punya jurnal akuntansi, currency '
                    'tidak diubah otomatis. Ubah manual di Settings bila perlu.',
                    company.name,
                )
                continue
            try:
                company.sudo().write({'currency_id': idr.id})
                _logger.info('UniTrade: currency company %s di-set ke IDR.', company.name)
            except Exception:  # noqa: BLE001
                _logger.exception('UniTrade: gagal set currency company %s ke IDR.', company.name)

        # 2) Website + pricelist publik -> IDR
        if 'website' in env:
            for website in env['website'].sudo().search([]):
                try:
                    pricelist = website.pricelist_id
                    if pricelist and pricelist.currency_id != idr:
                        pricelist.sudo().write({'currency_id': idr.id})
                except Exception:  # noqa: BLE001
                    _logger.exception('UniTrade: gagal set currency pricelist website %s.', website.id)

        # 3) SEMUA pricelist -> IDR (website bisa memakai pricelist lain per pengunjung)
        if 'product.pricelist' in env:
            stale_pricelists = env['product.pricelist'].sudo().search([
                ('currency_id', '!=', idr.id),
            ])
            for pricelist in stale_pricelists:
                try:
                    pricelist.write({'currency_id': idr.id})
                except Exception:  # noqa: BLE001
                    _logger.exception('UniTrade: gagal set currency pricelist %s.', pricelist.id)
            if stale_pricelists:
                _logger.info('UniTrade: %s pricelist di-set ke IDR.', len(stale_pricelists))

        # 4) Nonaktifkan USD agar tidak terpakai lagi di storefront (opsional, aman)
        usd = env.ref('base.USD', raise_if_not_found=False)
        if usd and usd.active and usd != idr:
            company_uses_usd = env['res.company'].sudo().search_count([('currency_id', '=', usd.id)])
            if not company_uses_usd:
                try:
                    usd.sudo().write({'active': False})
                    _logger.info('UniTrade: currency USD dinonaktifkan.')
                except Exception:  # noqa: BLE001
                    _logger.exception('UniTrade: gagal menonaktifkan USD.')

        # 5) Order draft (keranjang aktif) yang masih currency lama -> IDR.
        #    currency_id sale.order dihitung dari pricelist_id, sehingga order
        #    yang dibuat saat currency masih USD tidak otomatis berubah. Kita
        #    recompute manual agar keranjang & checkout yang sedang berjalan
        #    langsung memakai Rupiah.
        if 'sale.order' in env:
            draft_orders = env['sale.order'].sudo().search([
                ('state', '=', 'draft'),
                ('currency_id', '!=', idr.id),
            ])
            if draft_orders:
                try:
                    if hasattr(draft_orders, '_compute_currency_id'):
                        draft_orders._compute_currency_id()
                    # Pastikan benar-benar IDR walau pricelist belum sinkron
                    still_stale = draft_orders.filtered(lambda o: o.currency_id != idr)
                    if still_stale:
                        still_stale.write({'currency_id': idr.id})
                    _logger.info('UniTrade: %s keranjang draft di-set ke IDR.', len(draft_orders))
                except Exception:  # noqa: BLE001
                    _logger.exception('UniTrade: gagal recompute currency keranjang draft.')
