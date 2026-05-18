/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';
import { jsonrpc } from '@web/core/network/rpc_service';

publicWidget.registry.UnitradeProductDetailSkeleton =
  publicWidget.Widget.extend({
    selector: '#product_detail.ut-product-detail-hydrating',

    start() {
      const superPromise = this._super
        ? this._super.apply(this, arguments)
        : Promise.resolve();
      this._isRevealed = false;
      this._fallbackTimer = window.setTimeout(
        () => this._revealContent(),
        1800,
      );

      const revealAfterFrame = () => {
        window.requestAnimationFrame(() => {
          window.setTimeout(() => this._revealContent(), 180);
        });
      };

      if (document.readyState === 'complete') {
        revealAfterFrame();
      } else {
        this._onWindowLoad = revealAfterFrame;
        window.addEventListener('load', this._onWindowLoad, { once: true });
      }

      return superPromise;
    },

    destroy() {
      if (this._fallbackTimer) {
        window.clearTimeout(this._fallbackTimer);
      }
      if (this._onWindowLoad) {
        window.removeEventListener('load', this._onWindowLoad);
      }
      if (this._super) {
        this._super.apply(this, arguments);
      }
    },

    _revealContent() {
      if (this._isRevealed || !this.el) {
        return;
      }
      this._isRevealed = true;
      if (this._fallbackTimer) {
        window.clearTimeout(this._fallbackTimer);
        this._fallbackTimer = null;
      }
      this.el.classList.remove('ut-product-detail-hydrating');
      this.el.classList.add('ut-product-detail-loaded');
    },
  });

publicWidget.registry.UnitradeProductDetailHashTabs =
  publicWidget.Widget.extend({
    selector: '#product_detail',

    start() {
      const superPromise = this._super
        ? this._super.apply(this, arguments)
        : Promise.resolve();
      window.setTimeout(() => this._activateInitialTab(), 0);
      return superPromise;
    },

    _activateInitialTab() {
      const params = new URLSearchParams(window.location.search);
      if (
        window.location.hash !== '#tab-ulasan' &&
        params.get('tab') !== 'reviews'
      ) {
        return;
      }
      const reviewTab = document.getElementById('ut-tab-ulasan');
      const reviewPanel = document.getElementById('tab-ulasan');
      if (reviewTab) {
        reviewTab.click();
      }
      if (reviewPanel) {
        reviewPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    },
  });

publicWidget.registry.UnitradeProductWishlistDirect =
  publicWidget.Widget.extend({
    selector: '#product_detail',
    events: {
      'click .ut-product-wishlist-direct': '_onWishlistClick',
    },

    start() {
      this._hydrateWishlistState();
      return this._super(...arguments);
    },

    async _hydrateWishlistState() {
      const button = this.el.querySelector('.ut-product-wishlist-direct');
      if (!button) {
        return;
      }

      const productId = parseInt(button.dataset.productId, 10);
      if (!productId) {
        return;
      }

      try {
        const result = await jsonrpc('/unitrade/wishlist/status', {
          product_id: productId,
        });
        if (!result || result.success === false) {
          return;
        }
        this._setWishlistButtonState(button, Boolean(result.active));
      } catch (error) {
        console.debug('[UniTrade] Wishlist status:', error);
      }
    },

    async _onWishlistClick(ev) {
      ev.preventDefault();
      ev.stopPropagation();

      const button = ev.currentTarget;
      const productId = parseInt(button.dataset.productId, 10);
      if (!productId || button.disabled) {
        return;
      }

      button.disabled = true;
      button.classList.add('is-loading');

      try {
        const result = await jsonrpc('/unitrade/wishlist/toggle', {
          product_id: productId,
        });

        if (!result || result.success === false) {
          throw new Error(
            (result && result.message) || 'Wishlist update failed',
          );
        }

        const isActive = Boolean(result.added);
        this._setWishlistButtonState(button, isActive);
        this._showWishlistFeedback(
          button,
          isActive ? 'Ditambahkan ke wishlist' : 'Dihapus dari wishlist',
          isActive,
        );
      } catch (error) {
        if (error && (error.message || '').includes('Session expired')) {
          window.location.href = `/web/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
          return;
        }
        this._showWishlistFeedback(button, 'Wishlist gagal diperbarui', false);
        console.error('[UniTrade] Wishlist direct:', error);
      } finally {
        button.disabled = false;
        button.classList.remove('is-loading');
      }
    },

    _setWishlistButtonState(button, isActive) {
      button.dataset.active = isActive ? '1' : '0';
      button.classList.toggle('is-active', isActive);
      button.setAttribute(
        'title',
        isActive ? 'Lihat wishlist' : 'Tambahkan ke wishlist',
      );
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    },

    _showWishlistFeedback(button, message, showLink) {
      const wrapper = button.parentElement;
      if (!wrapper) {
        return;
      }

      let feedback = wrapper.querySelector('.ut-product-wishlist-feedback');
      if (!feedback) {
        feedback = document.createElement('a');
        feedback.className = 'ut-product-wishlist-feedback';
        wrapper.appendChild(feedback);
      }

      feedback.textContent = message;
      feedback.href = showLink ? '/my/wishlist' : '#';
      feedback.classList.toggle('is-link', showLink);
      feedback.classList.add('is-visible');

      window.clearTimeout(this._wishlistFeedbackTimer);
      this._wishlistFeedbackTimer = window.setTimeout(() => {
        feedback.classList.remove('is-visible');
      }, 2400);
    },
  });

publicWidget.registry.UnitradeProductStockWarning = publicWidget.Widget.extend({
  selector: '#product_detail',
  events: {
    "input input[name='add_qty']": '_onQuantityChanged',
    "change input[name='add_qty']": '_onQuantityChanged',
    'click #add_to_cart': '_onAddToCart',
  },

  start() {
    const result = this._super(...arguments);
    this._hasAttemptedSubmit = false;
    this._isSubmitting = false;
    window.unitradeValidateProductStock = this._validateStock.bind(this);
    this._onCaptureAddToCart = this._onCaptureAddToCart.bind(this);
    this._onCaptureSubmit = this._onCaptureSubmit.bind(this);
    document.addEventListener('click', this._onCaptureAddToCart, true);
    document.addEventListener('submit', this._onCaptureSubmit, true);
    this._hideWarning();
    return result;
  },

  destroy() {
    document.removeEventListener('click', this._onCaptureAddToCart, true);
    document.removeEventListener('submit', this._onCaptureSubmit, true);
    if (window.unitradeValidateProductStock) {
      delete window.unitradeValidateProductStock;
    }
    return this._super(...arguments);
  },

  _onQuantityChanged() {
    const warning = this.el.querySelector('[data-unitrade-stock-warning]');
    if (warning) {
      delete warning.dataset.serverMessage;
    }
    if (this._hasAttemptedSubmit) {
      this._validateStock();
    } else {
      this._hideWarning();
    }
  },

  _onAddToCart(ev) {
    const form = ev.currentTarget.closest('[data-unitrade-stock-form]');
    this._handleAddToCart(ev, form);
  },

  _onCaptureAddToCart(ev) {
    if (!ev.target.closest) {
      return;
    }
    const button = ev.target.closest('#add_to_cart');
    if (!button || !this.el.contains(button)) {
      return;
    }
    if (button.dataset.stockBlocked === '1') {
      ev.preventDefault();
      ev.stopPropagation();
      if (ev.stopImmediatePropagation) {
        ev.stopImmediatePropagation();
      }
      return;
    }
    this._handleAddToCart(ev, button.closest('[data-unitrade-stock-form]'));
  },

  _onCaptureSubmit(ev) {
    if (!ev.target.closest) {
      return;
    }
    const form = ev.target.closest('[data-unitrade-stock-form]');
    if (!form || !this.el.contains(form)) {
      return;
    }
    this._handleAddToCart(ev, form);
  },

  async _handleAddToCart(ev, scope) {
    ev.preventDefault();
    ev.stopPropagation();
    if (ev.stopImmediatePropagation) {
      ev.stopImmediatePropagation();
    }
    if (this._isSubmitting) {
      return;
    }
    const form = scope || this.el.querySelector('[data-unitrade-stock-form]');
    if (!form) {
      return;
    }
    this._hasAttemptedSubmit = true;
    if (!this._validateStock(form, true)) {
      return;
    }

    const button = form.querySelector('#add_to_cart');
    this._setSubmitting(button, true);
    try {
      const productInput = form.querySelector("input[name='product_id']");
      const qtyInput = form.querySelector("input[name='add_qty']");
      const result = await jsonrpc('/unitrade/product/stock/validate', {
        product_id: productInput ? Number(productInput.value) : 0,
        add_qty: qtyInput ? qtyInput.value : 0,
        include_cart: false,
      });
      if (result && result.valid === false) {
        this._showWarning(result.message || 'Stok tidak cukup.');
        this._setSubmitting(button, false);
        return;
      }
      if (HTMLFormElement.prototype.submit) {
        HTMLFormElement.prototype.submit.call(form);
      } else {
        form.submit();
      }
    } catch (error) {
      console.error('[UniTrade] Product stock validation failed:', error);
      this._showWarning(
        'Stok belum dapat divalidasi. Muat ulang halaman lalu coba lagi.',
      );
      this._setSubmitting(button, false);
    }
  },

  _validateStock(scope, showWarning = this._hasAttemptedSubmit) {
    const root = scope || this.el;
    const input = root.querySelector("input[name='add_qty']");
    const warning =
      root.querySelector('[data-unitrade-stock-warning]') ||
      this.el.querySelector('[data-unitrade-stock-warning]');
    const button =
      root.querySelector('#add_to_cart') ||
      this.el.querySelector('#add_to_cart');
    if (!input || !warning) {
      return true;
    }

    const maxAttr = input.dataset.max;
    const maxQty =
      maxAttr === undefined || maxAttr === '' ? null : Number(maxAttr);
    const qty = Number.parseFloat(input.value || '');
    const isQtyInvalid = !Number.isFinite(qty) || qty <= 0;
    const isStockInvalid =
      !isQtyInvalid &&
      maxQty !== null &&
      Number.isFinite(maxQty) &&
      qty > maxQty;
    const isInvalid = isQtyInvalid || isStockInvalid;

    input.classList.toggle('is-stock-invalid', isInvalid && showWarning);
    warning.classList.toggle('tw-hidden', !isInvalid || !showWarning);
    warning.classList.toggle('is-visible', isInvalid && showWarning);
    if (isQtyInvalid && showWarning) {
      this._showWarning('Jumlah produk tidak valid.');
    } else if (isStockInvalid && showWarning) {
      this._showWarning(
        `Stok tidak cukup. Stok tersedia hanya ${this._formatQty(maxQty)} item.`,
      );
    } else if (!isInvalid) {
      this._hideWarning();
    }
    if (button) {
      button.classList.toggle('disabled', isInvalid && showWarning);
    }
    return !isInvalid;
  },

  _showWarning(message) {
    const warning = this.el.querySelector('[data-unitrade-stock-warning]');
    if (!warning) {
      return;
    }
    warning.textContent = message;
    warning.classList.remove('tw-hidden');
    warning.classList.add('is-visible');
  },

  _hideWarning() {
    const warning = this.el.querySelector('[data-unitrade-stock-warning]');
    const input = this.el.querySelector("input[name='add_qty']");
    const button = this.el.querySelector('#add_to_cart');
    if (warning) {
      warning.classList.add('tw-hidden');
      warning.classList.remove('is-visible');
    }
    if (input) {
      input.classList.remove('is-stock-invalid');
    }
    if (button && !this._isSubmitting) {
      if (button.dataset.stockBlocked === '1') {
        button.disabled = true;
      } else {
        button.disabled = false;
        button.classList.remove('disabled');
      }
    }
  },

  _setSubmitting(button, isSubmitting) {
    this._isSubmitting = isSubmitting;
    if (!button) {
      return;
    }
    button.disabled = isSubmitting;
    button.classList.toggle('disabled', isSubmitting);
    button.classList.toggle('is-loading', isSubmitting);
  },

  _formatQty(qty) {
    if (Number.isInteger(qty)) {
      return String(qty);
    }
    return String(Math.max(qty, 0))
      .replace(/(\.\d*?)0+$/, '$1')
      .replace(/\.$/, '');
  },
});

publicWidget.registry.UnitradeProductImagePreview = publicWidget.Widget.extend({
  selector: '#product_detail',
  events: {
    'click [data-product-image-preview]': '_onOpenPreview',
  },

  start() {
    this._onKeydown = this._onKeydown.bind(this);
    document.addEventListener('keydown', this._onKeydown);
    return this._super(...arguments);
  },

  destroy() {
    document.removeEventListener('keydown', this._onKeydown);
    this._removePreview();
    return this._super(...arguments);
  },

  _onOpenPreview(ev) {
    ev.preventDefault();
    const trigger = ev.currentTarget;
    const image = trigger.querySelector('img');
    const src = trigger.dataset.previewSrc || (image && image.src);
    if (!src) {
      return;
    }

    this._removePreview();
    const modal = document.createElement('div');
    modal.className = 'ut-product-image-preview-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Preview gambar produk');
    modal.innerHTML = `
            <button type="button" class="ut-product-image-preview-backdrop" aria-label="Tutup preview"></button>
            <div class="ut-product-image-preview-dialog">
                <button type="button" class="ut-product-image-preview-close" aria-label="Tutup preview">
                    <i class="fa fa-times"></i>
                </button>
                <img src="${this._escapeAttribute(src)}" alt="${this._escapeAttribute(trigger.dataset.previewAlt || (image && image.alt) || 'Gambar produk')}"/>
            </div>
        `;

    modal
      .querySelectorAll(
        '.ut-product-image-preview-backdrop, .ut-product-image-preview-close',
      )
      .forEach((button) => {
        button.addEventListener('click', () => this._removePreview());
      });

    document.body.appendChild(modal);
    document.body.classList.add('ut-product-image-preview-open');
    this.previewModal = modal;
  },

  _onKeydown(ev) {
    if (ev.key === 'Escape' && this.previewModal) {
      this._removePreview();
    }
  },

  _removePreview() {
    if (this.previewModal) {
      this.previewModal.remove();
      this.previewModal = null;
    }
    document.body.classList.remove('ut-product-image-preview-open');
  },

  _escapeAttribute(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  },
});
