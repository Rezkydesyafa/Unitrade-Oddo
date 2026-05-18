/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

const PHOTO_MAX_FILES = 3;
const PHOTO_MAX_SIZE = 5 * 1024 * 1024;
const VIDEO_MAX_SIZE = 10 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
const VIDEO_TYPES = ["video/mp4", "video/webm"];

publicWidget.registry.UnitradeOrderRefundModal = publicWidget.Widget.extend({
    selector: ".ut-user-orders-main, .ut-refund-create-page",
    events: {
        "click [data-refund-open]": "_onOpen",
        "click [data-refund-close]": "_onClose",
        "change [data-refund-reason]": "_onReasonChange",
        "click [data-refund-browse]": "_onBrowseFiles",
        "change [data-refund-photos]": "_onPhotoChange",
        "change [data-refund-unboxing]": "_onVideoChange",
        "dragover [data-refund-dropzone]": "_onDropzoneDragOver",
        "dragleave [data-refund-dropzone]": "_onDropzoneDragLeave",
        "drop [data-refund-dropzone]": "_onDropzoneDrop",
        "submit [data-refund-form]": "_onSubmit",
    },

    start() {
        this.modal = this.el.querySelector("[data-order-refund-modal]");
        this.photoPreviewUrls = [];
        this._onKeydown = this._onKeydown.bind(this);
        document.addEventListener("keydown", this._onKeydown);
        this._syncUnboxingRequirement();
        return this._super(...arguments);
    },

    destroy() {
        document.removeEventListener("keydown", this._onKeydown);
        this._revokePhotoPreviews();
        this._super(...arguments);
    },

    _root() {
        return this.modal || this.el;
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
        this._clearUploadState();
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
        const root = this._root();
        const reason = root && root.querySelector("[data-refund-reason]");
        const videoInput = root && root.querySelector("[data-refund-unboxing]");
        const videoHint = root && root.querySelector("[data-refund-unboxing-hint]");
        const driveInput = root && root.querySelector("[data-refund-drive-url]");
        const driveHint = root && root.querySelector("[data-refund-drive-hint]");
        if (!reason || !driveInput) {
            return;
        }
        const required = ["not_as_described", "damaged", "wrong_item"].includes(reason.value);
        driveInput.required = required;
        if (videoInput) {
            videoInput.required = false;
        }
        if (driveHint) {
            driveHint.textContent = required
                ? "Wajib isi link Google Drive video unboxing untuk alasan ini."
                : "Opsional untuk alasan ini. Gunakan link Google Drive jika file terlalu besar.";
        }
        if (videoHint) {
            videoHint.textContent = required
                ? "Upload langsung tetap opsional sebagai bukti tambahan. Link Google Drive di bawah tetap wajib."
                : "MP4 atau WEBM. Opsional, maksimal 10 MB.";
        }
    },

    _onBrowseFiles(ev) {
        ev.preventDefault();
        const root = this._root();
        const type = ev.currentTarget.dataset.refundBrowse;
        const input = type === "video"
            ? root.querySelector("[data-refund-unboxing]")
            : root.querySelector("[data-refund-photos]");
        if (input) {
            input.click();
        }
    },

    _onPhotoChange(ev) {
        this._validatePhotos(ev.currentTarget);
        this._renderFileList(ev.currentTarget, "[data-refund-photo-list]");
    },

    _onVideoChange(ev) {
        this._validateVideo(ev.currentTarget);
        this._renderFileList(ev.currentTarget, "[data-refund-video-list]");
    },

    _onDropzoneDragOver(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.add("is-dragging");
    },

    _onDropzoneDragLeave(ev) {
        ev.currentTarget.classList.remove("is-dragging");
    },

    _onDropzoneDrop(ev) {
        ev.preventDefault();
        const zone = ev.currentTarget;
        zone.classList.remove("is-dragging");
        const root = this._root();
        const input = zone.dataset.refundDropzone === "video"
            ? root.querySelector("[data-refund-unboxing]")
            : root.querySelector("[data-refund-photos]");
        if (!input || !ev.originalEvent.dataTransfer) {
            return;
        }
        const droppedFiles = Array.from(ev.originalEvent.dataTransfer.files || []);
        this._assignFiles(input, droppedFiles);
        if (input.matches("[data-refund-unboxing]")) {
            this._onVideoChange({ currentTarget: input });
        } else {
            this._onPhotoChange({ currentTarget: input });
        }
    },

    _onSubmit(ev) {
        const root = this._root();
        const photosInput = root.querySelector("[data-refund-photos]");
        const videoInput = root.querySelector("[data-refund-unboxing]");
        const photoErrors = this._validatePhotos(photosInput);
        const videoErrors = this._validateVideo(videoInput);
        if (photoErrors.length || videoErrors.length) {
            ev.preventDefault();
        }
    },

    _assignFiles(input, files) {
        const dataTransfer = new DataTransfer();
        files.forEach((file) => dataTransfer.items.add(file));
        try {
            input.files = dataTransfer.files;
        } catch (error) {
            this._setUploadError(input.closest("[data-refund-dropzone]"), [
                "Browser tidak mengizinkan drag & drop file ini. Gunakan tombol Choose Files.",
            ]);
        }
    },

    _validatePhotos(input) {
        if (!input) {
            return [];
        }
        const files = Array.from(input.files || []);
        const errors = [];
        if (!files.length) {
            errors.push("Minimal upload 1 foto bukti pengembalian.");
        }
        if (files.length > PHOTO_MAX_FILES) {
            errors.push("Foto bukti maksimal 3 file.");
        }
        files.forEach((file) => {
            if (!PHOTO_TYPES.includes(file.type)) {
                errors.push(`${file.name} harus berformat JPG, PNG, atau WEBP.`);
            }
            if (file.size > PHOTO_MAX_SIZE) {
                errors.push(`${file.name} melebihi 5 MB.`);
            }
        });
        this._setUploadError(input.closest("[data-refund-dropzone]"), errors);
        return errors;
    },

    _validateVideo(input) {
        if (!input) {
            return [];
        }
        const files = Array.from(input.files || []);
        const errors = [];
        files.forEach((file) => {
            if (!VIDEO_TYPES.includes(file.type)) {
                errors.push(`${file.name} harus berformat MP4 atau WEBM.`);
            }
            if (file.size > VIDEO_MAX_SIZE) {
                errors.push(`${file.name} melebihi 10 MB. Upload ke Google Drive lalu isi link di bawah.`);
            }
        });
        this._setUploadError(input.closest("[data-refund-dropzone]"), errors);
        return errors;
    },

    _renderFileList(input, selector) {
        const root = this._root();
        const list = root.querySelector(selector);
        if (!list || !input) {
            return;
        }
        const files = Array.from(input.files || []);
        const isPhotoList = selector.includes("photo");
        if (isPhotoList) {
            this._revokePhotoPreviews();
            list.classList.add("is-photo-list");
        }
        list.innerHTML = "";
        files.forEach((file) => {
            const item = document.createElement(isPhotoList ? "article" : "span");
            item.className = isPhotoList ? "ut-order-refund-file-preview" : "ut-order-refund-file-pill";
            if (isPhotoList) {
                const image = document.createElement("img");
                const previewUrl = URL.createObjectURL(file);
                this.photoPreviewUrls.push(previewUrl);
                image.src = previewUrl;
                image.alt = `Preview ${file.name}`;
                const caption = document.createElement("span");
                caption.textContent = `${file.name} (${this._formatSize(file.size)})`;
                item.append(image, caption);
            } else {
                item.textContent = `${file.name} (${this._formatSize(file.size)})`;
            }
            list.appendChild(item);
        });
    },

    _formatSize(size) {
        return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    },

    _setUploadError(zone, errors) {
        if (!zone) {
            return;
        }
        zone.classList.toggle("has-error", Boolean(errors.length));
        let errorNode = zone.querySelector("[data-refund-upload-error]");
        if (!errorNode) {
            errorNode = document.createElement("div");
            errorNode.className = "ut-order-refund-upload-error";
            errorNode.dataset.refundUploadError = "1";
            zone.appendChild(errorNode);
        }
        errorNode.textContent = errors.join(" ");
    },

    _clearUploadState() {
        const root = this._root();
        if (!root) {
            return;
        }
        this._revokePhotoPreviews();
        root.querySelectorAll(".ut-order-refund-upload-card").forEach((zone) => {
            zone.classList.remove("has-error", "is-dragging");
            const errorNode = zone.querySelector("[data-refund-upload-error]");
            if (errorNode) {
                errorNode.textContent = "";
            }
        });
        root.querySelectorAll(".ut-order-refund-file-list").forEach((list) => {
            list.innerHTML = "";
        });
    },

    _setValue(selector, value) {
        const node = this._root().querySelector(selector);
        if (node) {
            node.value = value;
        }
    },

    _setText(selector, value) {
        const node = this._root().querySelector(selector);
        if (node) {
            node.textContent = value;
        }
    },

    _revokePhotoPreviews() {
        this.photoPreviewUrls.forEach((previewUrl) => URL.revokeObjectURL(previewUrl));
        this.photoPreviewUrls = [];
    },
});
