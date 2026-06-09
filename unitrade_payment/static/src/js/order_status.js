/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc_service";

publicWidget.registry.UnitradeOrderStatusRealtime = publicWidget.Widget.extend({
    selector: ".ut-order-status-page[data-order-status-progress-url]",
    events: {
        "click [data-order-status-proof-preview]": "_onOpenProofPreview",
        "click [data-order-status-preview-close]": "_onCloseProofPreview",
    },

    start() {
        this.progressUrl = this.el.dataset.orderStatusProgressUrl;
        this.accessToken = this.el.dataset.orderStatusAccessToken || "";
        this.refundCreateUrl = this.el.dataset.orderStatusRefundCreateUrl || "";
        this.pollInterval = 5000;
        this.previewModal = this.el.querySelector("[data-order-status-proof-preview-modal]");
        this.previewImage = this.el.querySelector("[data-order-status-proof-preview-image]");
        this.previewTitle = this.el.querySelector("[data-order-status-preview-title]");
        this.previewCaption = this.el.querySelector("[data-order-status-preview-caption]");
        this._refreshProgress = this._refreshProgress.bind(this);
        this._onVisibilityChange = this._onVisibilityChange.bind(this);
        this._onPreviewKeydown = this._onPreviewKeydown.bind(this);
        document.addEventListener("visibilitychange", this._onVisibilityChange);
        document.addEventListener("keydown", this._onPreviewKeydown);
        this._refreshProgress();
        this.timer = window.setInterval(this._refreshProgress, this.pollInterval);
        return this._super(...arguments);
    },

    destroy() {
        window.clearInterval(this.timer);
        this._closeProofPreview();
        document.removeEventListener("visibilitychange", this._onVisibilityChange);
        document.removeEventListener("keydown", this._onPreviewKeydown);
        this._super(...arguments);
    },

    _onVisibilityChange() {
        if (!document.hidden) {
            this._refreshProgress();
        }
    },

    _onPreviewKeydown(ev) {
        if (ev.key === "Escape") {
            this._closeProofPreview();
        }
    },

    _onOpenProofPreview(ev) {
        ev.preventDefault();
        const trigger = ev.currentTarget;
        const image = trigger && trigger.querySelector("img");
        const src = image && image.getAttribute("src");
        if (!src || !this.previewModal || !this.previewImage) {
            return;
        }

        const title = trigger.dataset.previewTitle || image.getAttribute("alt") || "Preview bukti";
        const caption = trigger.dataset.previewCaption || "";
        this.previewImage.setAttribute("src", src);
        this.previewImage.setAttribute("alt", title);
        if (this.previewTitle) {
            this.previewTitle.textContent = title;
        }
        if (this.previewCaption) {
            this.previewCaption.textContent = caption;
            this.previewCaption.hidden = !caption;
        }
        this.previewModal.classList.add("is-open");
        this.previewModal.setAttribute("aria-hidden", "false");
        document.body.classList.add("ut-order-status-proof-preview-open");

        const closeButton = this.previewModal.querySelector(".ut-order-status-proof-preview-close");
        if (closeButton) {
            closeButton.focus({ preventScroll: true });
        }
    },

    _onCloseProofPreview(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this._closeProofPreview();
    },

    _closeProofPreview() {
        if (!this.previewModal) {
            return;
        }
        this.previewModal.classList.remove("is-open");
        this.previewModal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("ut-order-status-proof-preview-open");
        if (this.previewImage) {
            this.previewImage.removeAttribute("src");
        }
    },

    async _refreshProgress() {
        if (!this.progressUrl || document.hidden) {
            return;
        }
        try {
            const params = {};
            if (this.accessToken) {
                params.access_token = this.accessToken;
            }
            const payload = await jsonrpc(this.progressUrl, params);
            if (!payload || payload.success === false) {
                return;
            }
            this._renderProgress(payload.progress_steps || [], payload);
            this._renderRefundAction(payload);
        } catch (error) {
            // Keep the existing server-rendered progress if polling is temporarily unavailable.
        }
    },

    _renderProgress(steps, payload = {}) {
        const progress = this.el.querySelector("[data-order-status-progress]");
        if (!progress) {
            return;
        }
        progress.style.setProperty("--ut-order-status-step-count", String(Math.max(steps.length, 1)));
        const nodes = Array.from(progress.querySelectorAll("[data-order-status-step]"));
        const shouldRebuild = nodes.length !== steps.length || steps.some((step, index) => {
            const node = nodes[index];
            return !node || node.dataset.stepKey !== step.key;
        });
        if (shouldRebuild) {
            progress.replaceChildren(...steps.map((step) => this._buildProgressStep(step)));
            this._renderRefundNote(payload, steps);
            return;
        }
        steps.forEach((step, index) => {
            const node = nodes.find((candidate) => candidate.dataset.stepKey === step.key) || nodes[index];
            if (!node) {
                return;
            }
            node.classList.toggle("is-done", Boolean(step.done));
            node.classList.toggle("is-active", Boolean(step.active));
            node.classList.toggle("is-failed", Boolean(step.failed));
            node.dataset.stepUrl = step.url || "";
            const label = node.querySelector(".ut-order-status-step-label");
            const status = node.querySelector(".ut-order-status-step-status");
            if (label) {
                label.textContent = step.label || "";
            } else {
                node.textContent = step.label || "";
            }
            if (status) {
                status.textContent = step.status || "";
            }
        });
        this._renderRefundNote(payload, steps);
    },

    _buildProgressStep(step) {
        const node = document.createElement("div");
        node.className = [
            "ut-order-status-step",
            step.done ? "is-done" : "",
            step.active ? "is-active" : "",
            step.failed ? "is-failed" : "",
        ].filter(Boolean).join(" ");
        node.dataset.orderStatusStep = "1";
        node.dataset.stepKey = step.key || "";
        node.dataset.stepUrl = step.url || "";

        const dot = document.createElement("span");
        dot.className = "ut-order-status-dot";
        const label = document.createElement("span");
        label.className = "ut-order-status-step-label";
        label.textContent = step.label || "";
        const status = document.createElement("span");
        status.className = "ut-order-status-step-status";
        status.textContent = step.status || "";

        node.append(dot, label, status);
        return node;
    },

    _renderRefundNote(payload, steps) {
        const progress = this.el.querySelector("[data-order-status-progress]");
        if (!progress) {
            return;
        }
        const refundUrl = payload.refund_detail_url || (steps.find((step) => step.url) || {}).url || "";
        let note = this.el.querySelector("[data-order-status-refund-note]");
        if (!refundUrl) {
            if (note) {
                note.remove();
            }
            return;
        }
        if (!note) {
            note = document.createElement("div");
            note.className = "ut-order-status-refund-progress-note";
            note.dataset.orderStatusRefundNote = "1";
            progress.insertAdjacentElement("afterend", note);
        }
        note.replaceChildren();
        const text = document.createElement("span");
        text.textContent = "Pengembalian tercatat pada pesanan ini.";
        const link = document.createElement("a");
        link.href = refundUrl;
        link.textContent = "Lihat Status Pengembalian";
        note.append(text, link);
    },

    _renderRefundAction(payload = {}) {
        const slots = this.el.querySelectorAll("[data-order-status-refund-action-slot]");
        if (!slots.length) {
            return;
        }
        slots.forEach((slot) => {
            const refundDetailUrl = payload.refund_detail_url || "";
            const canRefund = Boolean(payload.can_refund) && !refundDetailUrl;
            const refundCreateUrl = slot.dataset.refundCreateUrl || payload.refund_create_url || this.refundCreateUrl || "";
            slot.replaceChildren();
            if (!refundDetailUrl && !canRefund) {
                return;
            }
            const link = document.createElement("a");
            link.dataset.orderStatusRefundAction = "1";
            if (refundDetailUrl) {
                link.href = refundDetailUrl;
                link.className = "ut-order-status-secondary ut-order-status-refund-action";
                link.textContent = "Lihat Status Pengembalian";
            } else {
                link.href = refundCreateUrl;
                link.className = "ut-order-status-danger ut-order-status-refund-action";
                link.textContent = "Ajukan Pengembalian";
            }
            slot.append(link);
        });
    },
});
