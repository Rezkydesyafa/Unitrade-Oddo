/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

function parseCounts(value) {
    try {
        return JSON.parse(value || "{}");
    } catch (error) {
        return {};
    }
}

const RECEIVE_ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const RECEIVE_MAX_SIZE = 5 * 1024 * 1024;

function receiveFileError(file) {
    if (!file) {
        return "Foto bukti wajib diunggah.";
    }
    if (!RECEIVE_ALLOWED_TYPES.includes(file.type)) {
        return "Format foto harus PNG, JPG, atau WebP.";
    }
    if (file.size > RECEIVE_MAX_SIZE) {
        return "Ukuran foto maksimal 5 MB.";
    }
    return "";
}

function formatFileSize(size) {
    if (!size) {
        return "0 KB";
    }
    if (size >= 1024 * 1024) {
        return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${Math.ceil(size / 1024)} KB`;
}

export class UserOrdersTabs extends Component {
    static template = "unitrade_theme.UserOrdersTabs";
    static props = {
        active: String,
        counts: Object,
    };

    setup() {
        this.tabs = [
            { key: "all", label: "Semua" },
            { key: "unpaid", label: "Belum di bayar" },
            { key: "processing", label: "Di Proses" },
            { key: "done", label: "Selesai" },
            { key: "cancel", label: "Dibatalkan" },
            { key: "refund", label: "Pengembalian" },
        ];
        this.state = useState({
            active: this.props.active || "all",
        });
        onMounted(() => this.applyFilter());
    }

    tabClass(key) {
        return `ut-user-orders-filter-tab${this.state.active === key ? " is-active" : ""}`;
    }

    count(key) {
        return this.props.counts[key] || 0;
    }

    setStatus(key) {
        this.state.active = key;
        this.applyFilter();
        const url = new URL(window.location.href);
        if (key === "all") {
            url.searchParams.delete("status");
        } else {
            url.searchParams.set("status", key);
        }
        window.history.replaceState({}, "", url.toString());
    }

    applyFilter() {
        const list = document.querySelector("[data-orders-list]");
        if (!list) {
            return;
        }
        let visibleCount = 0;
        list.querySelectorAll(".ut-user-order-card").forEach((card) => {
            const visible = this.state.active === "all" || card.dataset.orderStatus === this.state.active;
            card.classList.toggle("ut-is-hidden", !visible);
            if (visible) {
                visibleCount += 1;
            }
        });

        const empty = list.querySelector(".ut-user-orders-filter-empty");
        if (empty) {
            empty.classList.toggle("ut-is-visible", visibleCount === 0 && list.querySelector(".ut-user-order-card"));
        }
    }
}

publicWidget.registry.UnitradeUserOrdersTabs = publicWidget.Widget.extend({
    selector: "#ut-user-orders-tabs",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        this.el.innerHTML = "";
        this.component = await mount(UserOrdersTabs, this.el, {
            props: {
                active: this.el.dataset.activeStatus || "all",
                counts: parseCounts(this.el.dataset.counts),
            },
            templates,
        });
        return superPromise;
    },

    destroy() {
        if (this.component && this.component.destroy) {
            this.component.destroy();
        }
        if (this._super) {
            this._super.apply(this, arguments);
        }
    },
});

publicWidget.registry.UnitradeUserOrderCards = publicWidget.Widget.extend({
    selector: ".ut-user-orders-list",
    events: {
        "click .ut-user-order-card": "_onCardClick",
        "keydown .ut-user-order-card": "_onCardKeydown",
    },

    _isInteractiveTarget(target) {
        return Boolean(target.closest(
            "a, button, input, textarea, select, label, form, .ut-user-order-actions, [data-review-open]"
        ));
    },

    _openCard(card) {
        const url = card && card.dataset.orderUrl;
        if (url) {
            window.location.href = url;
        }
    },

    _onCardClick(ev) {
        if (this._isInteractiveTarget(ev.target)) {
            return;
        }
        this._openCard(ev.currentTarget);
    },

    _onCardKeydown(ev) {
        if (ev.key !== "Enter" && ev.key !== " ") {
            return;
        }
        if (this._isInteractiveTarget(ev.target)) {
            return;
        }
        ev.preventDefault();
        this._openCard(ev.currentTarget);
    },
});

publicWidget.registry.UnitradeOrderReceiveModal = publicWidget.Widget.extend({
    selector: ".ut-user-orders-main",
    events: {
        "click [data-receive-open]": "_onOpen",
        "click [data-receive-close]": "_onClose",
        "click [data-receive-browse]": "_onBrowse",
        "change [data-receive-file]": "_onFileChange",
        "dragover [data-receive-dropzone]": "_onDragOver",
        "dragleave [data-receive-dropzone]": "_onDragLeave",
        "drop [data-receive-dropzone]": "_onDrop",
        "submit [data-receive-form]": "_onSubmit",
    },

    start() {
        this.modal = this.el.querySelector("[data-order-receive-modal]");
        this.receivePreviewUrl = "";
        this._onKeydown = this._onKeydown.bind(this);
        document.addEventListener("keydown", this._onKeydown);
        return this._super(...arguments);
    },

    destroy() {
        document.removeEventListener("keydown", this._onKeydown);
        this._clearReceivePreview();
        this._super(...arguments);
    },

    _onOpen(ev) {
        ev.preventDefault();
        const button = ev.currentTarget;
        if (!this.modal) {
            return;
        }
        this._reset();
        const form = this.modal.querySelector("[data-receive-form]");
        const ledgerInput = this.modal.querySelector("[data-receive-ledger-input]");
        const productName = this.modal.querySelector("[data-receive-product-name]");
        const sellerName = this.modal.querySelector("[data-receive-seller-name]");
        const image = this.modal.querySelector("[data-receive-product-image]");

        if (form) {
            form.action = button.dataset.receiveUrl || "";
        }
        if (ledgerInput) {
            ledgerInput.value = button.dataset.receiveLedgerId || "";
        }
        if (productName) {
            productName.textContent = button.dataset.receiveProductName || "Produk";
        }
        if (sellerName) {
            sellerName.textContent = button.dataset.receiveSellerName || "Nama toko";
        }
        if (image) {
            image.src = button.dataset.receiveImageUrl || "/web/static/img/placeholder.png";
        }

        this.modal.classList.add("is-open");
        this.modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("ut-order-receive-modal-open");
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
        document.body.classList.remove("ut-order-receive-modal-open");
        this._clearReceivePreview();
    },

    _onKeydown(ev) {
        if (ev.key === "Escape" && this.modal && this.modal.classList.contains("is-open")) {
            this._onClose(ev);
        }
    },

    _onBrowse(ev) {
        ev.preventDefault();
        const input = this.modal && this.modal.querySelector("[data-receive-file]");
        if (input) {
            input.click();
        }
    },

    _onFileChange(ev) {
        this._setFileFeedback(ev.currentTarget.files && ev.currentTarget.files[0]);
    },

    _onDragOver(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.add("is-dragging");
    },

    _onDragLeave(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("is-dragging");
    },

    _onDrop(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("is-dragging");
        const nativeEvent = ev.originalEvent || ev;
        const input = this.modal && this.modal.querySelector("[data-receive-file]");
        if (!input || !nativeEvent.dataTransfer || !nativeEvent.dataTransfer.files.length) {
            return;
        }
        try {
            input.files = nativeEvent.dataTransfer.files;
        } catch (error) {
            this._showError("Browser tidak mengizinkan drag & drop file ini. Gunakan tombol Choose Files.");
            return;
        }
        this._setFileFeedback(input.files[0]);
    },

    _onSubmit(ev) {
        const input = this.modal && this.modal.querySelector("[data-receive-file]");
        const file = input && input.files && input.files[0];
        const error = receiveFileError(file);
        if (error) {
            ev.preventDefault();
            this._showError(error);
        }
    },

    _setFileFeedback(file) {
        const error = receiveFileError(file);
        if (error) {
            this._showError(error);
            this._renderFile();
            return false;
        }
        this._clearError();
        this._renderFile(file);
        return true;
    },

    _renderFile(file) {
        const list = this.modal && this.modal.querySelector("[data-receive-file-list]");
        if (!list) {
            return;
        }
        this._clearReceivePreview();
        list.innerHTML = "";
        if (!file) {
            return;
        }
        const item = document.createElement("div");
        item.className = "ut-receive-file-item";
        const preview = document.createElement("img");
        this.receivePreviewUrl = URL.createObjectURL(file);
        preview.src = this.receivePreviewUrl;
        preview.alt = "Preview bukti barang diterima";
        preview.className = "ut-receive-file-preview";
        const text = document.createElement("div");
        text.className = "ut-receive-file-meta";
        const name = document.createElement("strong");
        name.textContent = file.name;
        const meta = document.createElement("span");
        meta.textContent = formatFileSize(file.size);
        text.append(name, meta);
        item.append(preview, text);
        list.appendChild(item);
    },

    _reset() {
        const form = this.modal && this.modal.querySelector("[data-receive-form]");
        if (form) {
            form.reset();
        }
        this._renderFile();
        this._clearError();
    },

    _clearReceivePreview() {
        if (this.receivePreviewUrl) {
            URL.revokeObjectURL(this.receivePreviewUrl);
            this.receivePreviewUrl = "";
        }
    },

    _showError(message) {
        const node = this.modal && this.modal.querySelector("[data-receive-error]");
        if (!node) {
            return;
        }
        node.textContent = message;
        node.classList.add("is-visible");
    },

    _clearError() {
        const node = this.modal && this.modal.querySelector("[data-receive-error]");
        if (!node) {
            return;
        }
        node.textContent = "";
        node.classList.remove("is-visible");
    },
});

publicWidget.registry.UnitradeOrderStatusUpload = publicWidget.Widget.extend({
    selector: ".ut-order-status-page",
    events: {
        "change .ut-order-status-upload-card input[type='file']": "_onFileChange",
        "dragover .ut-order-status-upload-card": "_onDragOver",
        "dragleave .ut-order-status-upload-card": "_onDragLeave",
        "drop .ut-order-status-upload-card": "_onDrop",
        "submit .ut-order-status-receive-box": "_onSubmit",
    },

    destroy() {
        this.el.querySelectorAll(".ut-order-status-upload-card").forEach((card) => this._clearUploadPreview(card));
        this._super(...arguments);
    },

    _onFileChange(ev) {
        this._syncUploadCard(ev.currentTarget);
    },

    _onDragOver(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.add("is-dragging");
    },

    _onDragLeave(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("is-dragging");
    },

    _onDrop(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("is-dragging");
        const nativeEvent = ev.originalEvent || ev;
        const input = ev.currentTarget.querySelector("input[type='file']");
        if (!input || !nativeEvent.dataTransfer || !nativeEvent.dataTransfer.files.length) {
            return;
        }
        try {
            input.files = nativeEvent.dataTransfer.files;
        } catch (error) {
            this._setUploadError(input, "Browser tidak mengizinkan drag & drop file ini. Gunakan tombol Choose Files.");
            return;
        }
        this._syncUploadCard(input);
    },

    _onSubmit(ev) {
        const input = ev.currentTarget.querySelector(".ut-order-status-upload-card input[type='file']");
        const file = input && input.files && input.files[0];
        const error = receiveFileError(file);
        if (error) {
            ev.preventDefault();
            this._setUploadError(input, error);
        }
    },

    _syncUploadCard(input) {
        const file = input && input.files && input.files[0];
        const error = receiveFileError(file);
        if (error) {
            this._setUploadError(input, error);
            return;
        }
        const card = input.closest(".ut-order-status-upload-card");
        if (!card) {
            return;
        }
        card.classList.add("has-file");
        this._setUploadPreview(card, file);
        const name = card.querySelector("[data-order-status-file-name]");
        if (name) {
            name.textContent = `${file.name} - ${formatFileSize(file.size)}`;
        }
        const errorNode = card.querySelector("[data-order-status-file-error]");
        if (errorNode) {
            errorNode.textContent = "";
        }
    },

    _setUploadError(input, message) {
        const card = input && input.closest(".ut-order-status-upload-card");
        if (!card) {
            return;
        }
        card.classList.remove("has-file");
        this._clearUploadPreview(card);
        const name = card.querySelector("[data-order-status-file-name]");
        if (name) {
            name.textContent = "";
        }
        const errorNode = card.querySelector("[data-order-status-file-error]");
        if (errorNode) {
            errorNode.textContent = message;
        }
    },

    _setUploadPreview(card, file) {
        const preview = card.querySelector("[data-order-status-file-preview]");
        if (!preview) {
            return;
        }
        this._clearUploadPreview(card);
        const previewUrl = URL.createObjectURL(file);
        card.dataset.uploadPreviewUrl = previewUrl;
        preview.src = previewUrl;
    },

    _clearUploadPreview(card) {
        const previewUrl = card && card.dataset.uploadPreviewUrl;
        if (previewUrl) {
            URL.revokeObjectURL(previewUrl);
            delete card.dataset.uploadPreviewUrl;
        }
        const preview = card && card.querySelector("[data-order-status-file-preview]");
        if (preview) {
            preview.removeAttribute("src");
        }
    },
});

publicWidget.registry.UnitradeOrderReviewModal = publicWidget.Widget.extend({
    selector: ".ut-user-orders-main",
    events: {
        "click [data-review-open]": "_onOpen",
        "click [data-review-close]": "_onClose",
        "click [data-review-star]": "_onSelectStar",
        "click [data-review-tag]": "_onToggleTag",
        "change [data-review-media-input]": "_onMediaChange",
        "click [data-review-remove-media]": "_onRemoveMedia",
        "click [data-review-submit]": "_onSubmit",
    },

    start() {
        this.modal = this.el.querySelector("[data-order-review-modal]");
        this.state = this._initialState();
        this._onKeydown = this._onKeydown.bind(this);
        document.addEventListener("keydown", this._onKeydown);
        this._syncReviewedButtons();
        return this._super(...arguments);
    },

    destroy() {
        document.removeEventListener("keydown", this._onKeydown);
        this._revokePreviews();
        this._super(...arguments);
    },

    _initialState() {
        return {
            productId: 0,
            orderId: 0,
            rating: 5,
            tags: [],
            images: [],
            triggerButton: null,
            submitting: false,
        };
    },

    _onOpen(ev) {
        ev.preventDefault();
        const button = ev.currentTarget;
        if (!this.modal) {
            return;
        }
        this._resetForm();
        this.state.productId = Number(button.dataset.reviewProductId || 0);
        this.state.orderId = Number(button.dataset.reviewOrderId || 0);
        this.state.triggerButton = button;

        const productName = this.modal.querySelector("[data-review-product-name]");
        const sellerName = this.modal.querySelector("[data-review-seller-name]");
        const image = this.modal.querySelector("[data-review-product-image]");
        if (productName) {
            productName.textContent = button.dataset.reviewProductName || "Produk";
        }
        if (sellerName) {
            sellerName.textContent = button.dataset.reviewSellerName || "Nama toko";
        }
        if (image) {
            image.src = button.dataset.reviewImageUrl || "/web/static/img/placeholder.png";
        }

        this.modal.classList.add("is-open");
        this.modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("ut-order-review-modal-open");
        this._syncStars();
        this._syncTags();

        const comment = this.modal.querySelector("[data-review-comment]");
        if (comment) {
            window.setTimeout(() => comment.focus(), 50);
        }
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
        document.body.classList.remove("ut-order-review-modal-open");
    },

    _onKeydown(ev) {
        if (ev.key === "Escape" && this.modal && this.modal.classList.contains("is-open")) {
            this._onClose(ev);
        }
    },

    _onSelectStar(ev) {
        ev.preventDefault();
        this.state.rating = Number(ev.currentTarget.dataset.reviewStar || 5);
        this._syncStars();
    },

    _onToggleTag(ev) {
        ev.preventDefault();
        const tag = ev.currentTarget.dataset.reviewTag;
        if (!tag) {
            return;
        }
        if (this.state.tags.includes(tag)) {
            this.state.tags = this.state.tags.filter((item) => item !== tag);
        } else {
            this.state.tags = this.state.tags.concat(tag);
        }
        this._syncTags();
    },

    async _onMediaChange(ev) {
        const files = Array.from(ev.currentTarget.files || []);
        ev.currentTarget.value = "";
        if (!files.length) {
            return;
        }
        this._clearMessage();

        if (this.state.images.length + files.length > 3) {
            this._showMessage("Maksimal 3 gambar untuk satu ulasan.", true);
            return;
        }

        const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
        for (const file of files) {
            if (!allowedTypes.includes(file.type)) {
                this._showMessage("Format gambar harus JPG, PNG, atau WebP.", true);
                return;
            }
            if (file.size >= 2 * 1024 * 1024) {
                this._showMessage("Ukuran setiap gambar harus kurang dari 2 MB.", true);
                return;
            }
        }

        try {
            const images = await Promise.all(files.map((file) => this._readFile(file)));
            this.state.images = this.state.images.concat(images).slice(0, 3);
            this._renderMediaPreview();
        } catch (error) {
            console.error("[UniTrade] Review image:", error);
            this._showMessage("Gambar gagal dibaca.", true);
        }
    },

    _onRemoveMedia(ev) {
        ev.preventDefault();
        const index = Number(ev.currentTarget.dataset.reviewRemoveMedia);
        const image = this.state.images[index];
        if (image && image.previewUrl) {
            URL.revokeObjectURL(image.previewUrl);
        }
        this.state.images.splice(index, 1);
        this._renderMediaPreview();
    },

    async _onSubmit(ev) {
        ev.preventDefault();
        if (this.state.submitting) {
            return;
        }
        const comment = (this.modal.querySelector("[data-review-comment]") || {}).value || "";
        if (!this.state.productId || !this.state.orderId) {
            this._showMessage("Data produk atau pesanan tidak valid.", true);
            return;
        }
        if (this.state.rating < 1 || this.state.rating > 5) {
            this._showMessage("Rating wajib dipilih.", true);
            return;
        }

        this.state.submitting = true;
        const submit = this.modal.querySelector("[data-review-submit]");
        if (submit) {
            submit.disabled = true;
            submit.textContent = "Mengirim...";
        }
        this._clearMessage();

        try {
            const result = await jsonrpc("/unitrade/reviews/create", {
                product_id: this.state.productId,
                order_id: this.state.orderId,
                rating: this.state.rating,
                tags: this.state.tags,
                comment: comment.trim(),
                images: this.state.images.map((image) => image.dataUrl),
            });
            if (!result || !result.success) {
                this._showMessage((result && result.message) || "Ulasan gagal dikirim.", true);
                return;
            }
            this._markReviewed();
            this._showMessage(result.message || "Ulasan berhasil dikirim.", false);
            window.setTimeout(() => this._onClose(), 450);
        } catch (error) {
            console.error("[UniTrade] Submit order review:", error);
            this._showMessage("Ulasan gagal dikirim.", true);
        } finally {
            this.state.submitting = false;
            if (submit) {
                submit.disabled = false;
                submit.textContent = "Ok";
            }
        }
    },

    _resetForm() {
        this._revokePreviews();
        this.state = this._initialState();
        const comment = this.modal.querySelector("[data-review-comment]");
        const input = this.modal.querySelector("[data-review-media-input]");
        if (comment) {
            comment.value = "";
        }
        if (input) {
            input.value = "";
        }
        this._renderMediaPreview();
        this._clearMessage();
    },

    _syncStars() {
        this.modal.querySelectorAll("[data-review-star]").forEach((button) => {
            const active = Number(button.dataset.reviewStar) <= this.state.rating;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-checked", active ? "true" : "false");
        });
    },

    _syncTags() {
        this.modal.querySelectorAll("[data-review-tag]").forEach((button) => {
            button.classList.toggle("is-active", this.state.tags.includes(button.dataset.reviewTag));
        });
    },

    _renderMediaPreview() {
        const preview = this.modal.querySelector("[data-review-media-preview]");
        if (!preview) {
            return;
        }
        preview.innerHTML = "";
        this.state.images.forEach((image, index) => {
            const item = document.createElement("div");
            item.className = "ut-order-review-media-item";
            item.innerHTML = `
                <img src="${image.previewUrl}" alt="Preview gambar ulasan ${index + 1}"/>
                <button type="button" data-review-remove-media="${index}" aria-label="Hapus gambar">&times;</button>
            `;
            preview.appendChild(item);
        });
    },

    _readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            const previewUrl = URL.createObjectURL(file);
            reader.onload = () => resolve({
                name: file.name,
                dataUrl: reader.result,
                previewUrl,
            });
            reader.onerror = () => {
                URL.revokeObjectURL(previewUrl);
                reject(reader.error || new Error("File read failed"));
            };
            reader.readAsDataURL(file);
        });
    },

    _revokePreviews() {
        (this.state && this.state.images || []).forEach((image) => {
            if (image.previewUrl) {
                URL.revokeObjectURL(image.previewUrl);
            }
        });
    },

    _markReviewed() {
        const button = this.state.triggerButton;
        if (!button) {
            return;
        }
        this._disableReviewButton(button, "Sudah Ulasan");
    },

    async _syncReviewedButtons() {
        const buttons = Array.from(this.el.querySelectorAll("[data-review-open]"));
        if (!buttons.length) {
            return;
        }

        const productIds = Array.from(new Set(
            buttons
                .map((button) => Number(button.dataset.reviewProductId || 0))
                .filter((productId) => productId > 0)
        ));
        if (!productIds.length) {
            return;
        }

        try {
            const result = await jsonrpc("/unitrade/reviews/status", {
                product_ids: productIds,
            });
            if (!result || !result.success || !result.status) {
                return;
            }

            buttons.forEach((button) => {
                const productId = String(Number(button.dataset.reviewProductId || 0));
                const status = result.status[productId];
                if (status && status.reviewed) {
                    this._disableReviewButton(button, "Sudah Ulasan");
                }
            });
        } catch (error) {
            console.error("[UniTrade] Review status:", error);
        }
    },

    _disableReviewButton(button, text) {
        if (!button) {
            return;
        }
        const replacement = document.createElement("button");
        replacement.type = "button";
        replacement.disabled = true;
        replacement.setAttribute("aria-disabled", "true");
        replacement.className = "ut-user-order-btn ut-user-order-btn-disabled";
        replacement.textContent = text || "Sudah Ulasan";
        button.replaceWith(replacement);
    },

    _showMessage(message, isError) {
        const node = this.modal.querySelector("[data-review-message]");
        if (!node) {
            return;
        }
        node.textContent = message;
        node.classList.add("is-visible");
        node.classList.toggle("is-error", Boolean(isError));
    },

    _clearMessage() {
        const node = this.modal.querySelector("[data-review-message]");
        if (!node) {
            return;
        }
        node.textContent = "";
        node.classList.remove("is-visible", "is-error");
    },
});
