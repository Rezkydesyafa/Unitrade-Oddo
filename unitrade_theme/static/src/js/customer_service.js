/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

const MAX_EVIDENCE_SIZE = 5 * 1024 * 1024;
const ALLOWED_EVIDENCE_TYPES = ["image/jpeg", "image/png", "video/mp4"];

function formatFileSize(size) {
    if (!size) {
        return "0 KB";
    }
    if (size >= 1024 * 1024) {
        return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${Math.ceil(size / 1024)} KB`;
}

function evidenceError(file) {
    if (!ALLOWED_EVIDENCE_TYPES.includes(file.type)) {
        return "Format bukti harus JPG, PNG, atau MP4.";
    }
    if (file.size > MAX_EVIDENCE_SIZE) {
        return "Ukuran setiap bukti maksimal 5 MB.";
    }
    return "";
}

function readEvidenceFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        const previewUrl = URL.createObjectURL(file);
        reader.onload = () => resolve({
            name: file.name,
            type: file.type,
            size: file.size,
            data: reader.result,
            previewUrl,
        });
        reader.onerror = () => {
            URL.revokeObjectURL(previewUrl);
            reject(reader.error || new Error("File read failed"));
        };
        reader.readAsDataURL(file);
    });
}

export class CustomerServicePage extends Component {
    static template = "unitrade_theme.CustomerServicePage";

    setup() {
        this.evidenceInput = useRef("evidenceInput");
        this.nextFileId = 1;
        this.toastTimer = null;
        this.state = useState({
            loading: true,
            submitting: false,
            categories: [],
            orders: [],
            recentTickets: [],
            allTicketsUrl: "/my/customer-service/tickets",
            error: "",
            toast: "",
            toastType: "success",
            evidence: [],
            form: {
                category: "",
                orderRef: "",
                title: "",
                description: "",
            },
        });
        onMounted(() => this.loadData());
        onWillUnmount(() => {
            this.revokeEvidencePreviews();
            if (this.toastTimer) {
                window.clearTimeout(this.toastTimer);
            }
        });
    }

    async loadData() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/customer-service/data", {});
            if (!result || !result.success) {
                this.state.error = (result && result.message) || "Data customer service gagal dimuat.";
                return;
            }
            this.state.categories = result.categories || [];
            this.state.orders = result.orders || [];
            this.state.recentTickets = result.recent_tickets || [];
            this.state.allTicketsUrl = result.all_tickets_url || "/my/customer-service/tickets";
        } catch (error) {
            console.error("[UniTrade] Customer service data:", error);
            this.state.error = "Data customer service gagal dimuat.";
        } finally {
            this.state.loading = false;
        }
    }

    categoryCardClass(category) {
        const selected = this.state.form.category === category.key ? " is-selected" : "";
        return `ut-cs-category-card is-${category.tone}${selected}`;
    }

    selectCategory(key) {
        this.state.form.category = key;
        this.state.error = "";
    }

    browseEvidence() {
        if (this.evidenceInput.el) {
            this.evidenceInput.el.click();
        }
    }

    async onEvidenceInput(ev) {
        const files = Array.from(ev.currentTarget.files || []);
        ev.currentTarget.value = "";
        await this.addEvidenceFiles(files);
    }

    onEvidenceDrag(ev) {
        ev.currentTarget.classList.add("is-dragging");
    }

    onEvidenceDragLeave(ev) {
        ev.currentTarget.classList.remove("is-dragging");
    }

    async onEvidenceDrop(ev) {
        ev.currentTarget.classList.remove("is-dragging");
        const nativeEvent = ev.originalEvent || ev;
        const files = Array.from(nativeEvent.dataTransfer ? nativeEvent.dataTransfer.files : []);
        await this.addEvidenceFiles(files);
    }

    async addEvidenceFiles(files) {
        if (!files.length) {
            return;
        }
        this.state.error = "";
        for (const file of files) {
            const error = evidenceError(file);
            if (error) {
                this.state.error = error;
                return;
            }
        }
        try {
            const readFiles = await Promise.all(files.map((file) => readEvidenceFile(file)));
            readFiles.forEach((file) => {
                file.id = this.nextFileId++;
                this.state.evidence.push(file);
            });
        } catch (error) {
            console.error("[UniTrade] Evidence upload:", error);
            this.state.error = "File bukti gagal dibaca.";
        }
    }

    removeEvidence(fileId) {
        const index = this.state.evidence.findIndex((file) => file.id === fileId);
        if (index < 0) {
            return;
        }
        const [file] = this.state.evidence.splice(index, 1);
        if (file && file.previewUrl) {
            URL.revokeObjectURL(file.previewUrl);
        }
    }

    revokeEvidencePreviews() {
        this.state.evidence.forEach((file) => {
            if (file.previewUrl) {
                URL.revokeObjectURL(file.previewUrl);
            }
        });
        this.state.evidence.splice(0, this.state.evidence.length);
    }

    validateForm() {
        if (!this.state.form.category) {
            return "Kategori masalah wajib dipilih.";
        }
        if (!this.state.form.title.trim()) {
            return "Judul masalah wajib diisi.";
        }
        if (!this.state.form.description.trim()) {
            return "Deskripsi keluhan wajib diisi.";
        }
        return "";
    }

    async submitTicket() {
        if (this.state.submitting) {
            return;
        }
        const error = this.validateForm();
        if (error) {
            this.state.error = error;
            return;
        }
        this.state.submitting = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/customer-service/ticket/create", {
                category: this.state.form.category,
                order_ref: this.state.form.orderRef.trim(),
                title: this.state.form.title.trim(),
                description: this.state.form.description.trim(),
                evidence_files: this.state.evidence.map((file) => ({
                    name: file.name,
                    mimetype: file.type,
                    size: file.size,
                    data: file.data,
                })),
            });
            if (!result || !result.success) {
                this.state.error = (result && result.message) || "Tiket gagal dikirim.";
                this.showToast(this.state.error, "error");
                return;
            }
            this.state.recentTickets = result.recent_tickets || this.state.recentTickets;
            this.resetForm();
            this.showToast(result.message || "Tiket berhasil dikirim.", "success");
        } catch (error) {
            console.error("[UniTrade] Submit customer ticket:", error);
            this.state.error = "Tiket gagal dikirim.";
            this.showToast(this.state.error, "error");
        } finally {
            this.state.submitting = false;
        }
    }

    resetForm() {
        this.revokeEvidencePreviews();
        this.state.form.category = "";
        this.state.form.orderRef = "";
        this.state.form.title = "";
        this.state.form.description = "";
    }

    showToast(message, type = "success") {
        this.state.toast = message;
        this.state.toastType = type;
        if (this.toastTimer) {
            window.clearTimeout(this.toastTimer);
        }
        this.toastTimer = window.setTimeout(() => {
            this.state.toast = "";
            this.toastTimer = null;
        }, 3600);
    }

    formatFileSize(size) {
        return formatFileSize(size);
    }
}

publicWidget.registry.UnitradeCustomerServicePage = publicWidget.Widget.extend({
    selector: "#ut-customer-service-app",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        this.el.innerHTML = "";
        this.component = await mount(CustomerServicePage, this.el, { templates });
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

publicWidget.registry.UnitradeCustomerTicketReply = publicWidget.Widget.extend({
    selector: "[data-cs-reply-form]",
    events: {
        submit: "_onSubmit",
    },

    start() {
        this.messageEl = this.el.querySelector("[data-cs-reply-message]");
        this.textarea = this.el.querySelector('textarea[name="body"]');
        this.submitButton = this.el.querySelector('button[type="submit"]');
        return this._super ? this._super.apply(this, arguments) : Promise.resolve();
    },

    _setMessage(message, type) {
        if (!this.messageEl) {
            return;
        }
        this.messageEl.textContent = message || "";
        this.messageEl.classList.remove("tw-hidden", "is-error", "is-success");
        this.messageEl.classList.add(type === "error" ? "is-error" : "is-success");
    },

    async _onSubmit(ev) {
        ev.preventDefault();
        const url = this.el.dataset.replyUrl;
        const body = (this.textarea && this.textarea.value ? this.textarea.value : "").trim();
        if (!url || !body) {
            this._setMessage("Balasan tidak boleh kosong.", "error");
            return;
        }
        if (this.submitButton) {
            this.submitButton.disabled = true;
            this.submitButton.textContent = "Mengirim...";
        }
        try {
            const result = await jsonrpc(url, { body });
            if (!result || !result.success) {
                this._setMessage((result && result.message) || "Balasan gagal dikirim.", "error");
                return;
            }
            this._setMessage(result.message || "Balasan terkirim.", "success");
            window.setTimeout(() => window.location.reload(), 650);
        } catch (error) {
            console.error("[UniTrade] Customer ticket reply:", error);
            this._setMessage("Balasan gagal dikirim.", "error");
        } finally {
            if (this.submitButton) {
                this.submitButton.disabled = false;
                this.submitButton.textContent = "Kirim Balasan";
            }
        }
    },
});
