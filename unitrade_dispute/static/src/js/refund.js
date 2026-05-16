/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.UnitradeOrderRefundModal = publicWidget.Widget.extend({
    selector: ".ut-user-orders-main",
    events: {
        "click [data-refund-open]": "_onOpen",
        "click [data-refund-close]": "_onClose",
        "change [data-refund-reason]": "_onReasonChange",
    },

    start() {
        this.modal = this.el.querySelector("[data-order-refund-modal]");
        this._onKeydown = this._onKeydown.bind(this);
        document.addEventListener("keydown", this._onKeydown);
        return this._super(...arguments);
    },

    destroy() {
        document.removeEventListener("keydown", this._onKeydown);
        this._super(...arguments);
    },

    _onOpen(ev) {
        ev.preventDefault();
        if (!this.modal) {
            return;
        }
        const button = ev.currentTarget;
        const form = this.modal.querySelector("[data-refund-form]");
        if (form) {
            form.action = button.dataset.refundUrl || "";
            form.reset();
        }
        this._setValue("[data-refund-ledger-id]", button.dataset.refundLedgerId || "");
        this._setValue("[data-refund-line-id]", button.dataset.refundLineId || "");
        this._setText("[data-refund-product-name]", button.dataset.refundProductName || "Produk");
        this._setText("[data-refund-seller-name]", button.dataset.refundSellerName || "Penjual UniTrade");
        this._setText("[data-refund-amount]", button.dataset.refundAmount || "-");
        this.modal.classList.add("is-open");
        this.modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("ut-refund-modal-open");
        this._syncUnboxingRequirement();
    },

    _onClose(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (!this.modal) {
            return;
        }
        this.modal.classList.remove("is-open");
        this.modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("ut-refund-modal-open");
    },

    _onKeydown(ev) {
        if (ev.key === "Escape" && this.modal && this.modal.classList.contains("is-open")) {
            this._onClose(ev);
        }
    },

    _onReasonChange() {
        this._syncUnboxingRequirement();
    },

    _syncUnboxingRequirement() {
        const reason = this.modal && this.modal.querySelector("[data-refund-reason]");
        const input = this.modal && this.modal.querySelector("[data-refund-unboxing]");
        const hint = this.modal && this.modal.querySelector("[data-refund-unboxing-hint]");
        if (!reason || !input) {
            return;
        }
        const required = ["not_as_described", "damaged", "wrong_item"].includes(reason.value);
        input.required = required;
        if (hint) {
            hint.textContent = required
                ? "Wajib untuk alasan barang tidak sesuai, rusak, atau salah barang."
                : "Opsional, tetapi membantu proses review.";
        }
    },

    _setValue(selector, value) {
        const node = this.modal.querySelector(selector);
        if (node) {
            node.value = value;
        }
    },

    _setText(selector, value) {
        const node = this.modal.querySelector(selector);
        if (node) {
            node.textContent = value;
        }
    },
});
