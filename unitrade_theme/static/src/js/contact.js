/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

publicWidget.registry.UnitradeContactPage = publicWidget.Widget.extend({
    selector: ".ut-contact-page",

    start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        this.form = this.el.querySelector("#contactus_form");
        this.submitButton = this.el.querySelector(".ut-contact-submit");
        this.toast = this.el.querySelector("[data-contact-toast]");
        this.successMessage = this.el.querySelector(".s_website_form_end_message");
        this.toastTimer = null;
        this.loadingTimer = null;
        this.lastToastMessage = "";

        if (this.form) {
            this.onSubmitAttempt = this._onSubmitAttempt.bind(this);
            this.onInput = this._onInput.bind(this);
            this.form.addEventListener("submit", this.onSubmitAttempt, true);
            this.form.addEventListener("input", this.onInput, true);
        }
        if (this.submitButton) {
            this.submitButton.addEventListener("click", this.onSubmitAttempt, true);
        }
        this._setupResultObserver();
        return superPromise;
    },

    destroy() {
        if (this.form) {
            this.form.removeEventListener("submit", this.onSubmitAttempt, true);
            this.form.removeEventListener("input", this.onInput, true);
        }
        if (this.submitButton) {
            this.submitButton.removeEventListener("click", this.onSubmitAttempt, true);
        }
        if (this.observer) {
            this.observer.disconnect();
        }
        if (this.toastTimer) {
            window.clearTimeout(this.toastTimer);
        }
        if (this.loadingTimer) {
            window.clearTimeout(this.loadingTimer);
        }
        if (this._super) {
            this._super.apply(this, arguments);
        }
    },

    _onSubmitAttempt(ev) {
        if (!this.form) {
            return;
        }
        const message = this._validateForm();
        if (message) {
            ev.preventDefault();
            ev.stopImmediatePropagation();
            this._setSubmitting(false);
            this._showToast(message, "error");
            return false;
        }
        this._setSubmitting(true);
    },

    _onInput(ev) {
        const input = ev.target.closest(".s_website_form_input");
        if (!input) {
            return;
        }
        input.setCustomValidity("");
        input.classList.remove("is-invalid");
        const field = input.closest(".s_website_form_field");
        if (field) {
            field.classList.remove("o_has_error");
        }
    },

    _validateForm() {
        const fields = [
            { selector: "#contact1", message: "Nama lengkap wajib diisi." },
            { selector: "#contact3", message: "Email wajib diisi." },
            { selector: "#contact5", message: "Subjek wajib diisi." },
            { selector: "#contact6", message: "Pesan wajib diisi." },
        ];
        let firstInvalid = null;
        let message = "";
        fields.forEach((field) => {
            const input = this.form.querySelector(field.selector);
            if (!input) {
                return;
            }
            input.setCustomValidity("");
            const invalid = !String(input.value || "").trim();
            if (invalid) {
                input.setCustomValidity(field.message);
                this._markInvalid(input);
                if (!firstInvalid) {
                    firstInvalid = input;
                    message = field.message;
                }
            }
        });

        const emailInput = this.form.querySelector("#contact3");
        const email = emailInput ? String(emailInput.value || "").trim() : "";
        if (email && !EMAIL_PATTERN.test(email)) {
            const emailMessage = "Format email belum valid.";
            emailInput.setCustomValidity(emailMessage);
            this._markInvalid(emailInput);
            if (!firstInvalid) {
                firstInvalid = emailInput;
                message = emailMessage;
            }
        }

        if (firstInvalid) {
            firstInvalid.focus({ preventScroll: true });
            firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        return message;
    },

    _markInvalid(input) {
        input.classList.add("is-invalid");
        const field = input.closest(".s_website_form_field");
        if (field) {
            field.classList.add("o_has_error");
        }
    },

    _setSubmitting(isSubmitting) {
        if (!this.form) {
            return;
        }
        this.form.classList.toggle("is-submitting", Boolean(isSubmitting));
        if (this.submitButton) {
            this.submitButton.setAttribute("aria-busy", isSubmitting ? "true" : "false");
        }
        if (this.loadingTimer) {
            window.clearTimeout(this.loadingTimer);
            this.loadingTimer = null;
        }
        if (isSubmitting) {
            this.loadingTimer = window.setTimeout(() => this._setSubmitting(false), 12000);
        }
    },

    _setupResultObserver() {
        const target = this.el.querySelector(".ut-contact-form");
        if (!target) {
            return;
        }
        this.observer = new MutationObserver(() => this._handleFormResult());
        this.observer.observe(target, {
            attributes: true,
            childList: true,
            subtree: true,
            characterData: true,
        });
    },

    _handleFormResult() {
        if (this.successMessage && !this.successMessage.classList.contains("d-none")) {
            this._setSubmitting(false);
            this._showToast("Pesan berhasil dikirim.", "success");
            return;
        }
        const result = this.el.querySelector("#s_website_form_result, #o_website_form_result");
        const text = result ? String(result.textContent || "").trim() : "";
        if (text) {
            this._setSubmitting(false);
            this._showToast("Pesan gagal dikirim. Periksa kembali form Anda.", "error");
        }
    },

    _showToast(message, type) {
        if (!this.toast || !message || this.lastToastMessage === `${type}:${message}`) {
            return;
        }
        this.lastToastMessage = `${type}:${message}`;
        this.toast.textContent = message;
        this.toast.classList.toggle("is-error", type === "error");
        this.toast.classList.add("is-visible");
        if (this.toastTimer) {
            window.clearTimeout(this.toastTimer);
        }
        this.toastTimer = window.setTimeout(() => {
            this.toast.classList.remove("is-visible");
            this.lastToastMessage = "";
        }, 3600);
    },
});
