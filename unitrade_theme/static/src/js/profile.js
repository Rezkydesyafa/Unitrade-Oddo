/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc_service";

publicWidget.registry.UnitradeUserProfileForm = publicWidget.Widget.extend({
    selector: ".ut-user-profile-form",
    events: {
        "change [data-profile-avatar-input]": "_onAvatarChange",
        "click .ut-user-profile-avatar-picker": "_onAvatarPickerClick",
        "click [data-profile-edit]": "_onEdit",
    },

    start() {
        this._setEditing(this.el.dataset.editing === "1");
        return this._super(...arguments);
    },

    _onEdit() {
        this._setEditing(true);
        const firstInput = this.el.querySelector("input[name='name']");
        if (firstInput) {
            firstInput.focus();
            firstInput.select();
        }
    },

    _onAvatarChange(ev) {
        const file = ev.currentTarget.files && ev.currentTarget.files[0];
        const preview = this.el.querySelector(".ut-user-profile-avatar-img");
        if (!file || !preview || !file.type.startsWith("image/")) {
            return;
        }
        const reader = new FileReader();
        reader.addEventListener("load", () => {
            preview.src = reader.result;
        });
        reader.readAsDataURL(file);
    },

    _onAvatarPickerClick(ev) {
        const input = this.el.querySelector("[data-profile-avatar-input]");
        if (!this.el.classList.contains("is-editing")) {
            ev.preventDefault();
            return;
        }
        if (ev.target === input || !input || input.disabled) {
            return;
        }
        ev.preventDefault();
        input.click();
    },

    _setEditing(isEditing) {
        this.el.dataset.editing = isEditing ? "1" : "0";
        this.el.classList.toggle("is-editing", isEditing);
        this.el.classList.toggle("is-readonly", !isEditing);

        this.el.querySelectorAll("[data-profile-control]").forEach((control) => {
            control.disabled = !isEditing;
        });
    },
});

publicWidget.registry.UnitradeSettingsNotifications = publicWidget.Widget.extend({
    selector: "[data-settings-notifications]",
    events: {
        "change [data-notification-field]": "_onToggle",
    },

    async _onToggle(ev) {
        const input = ev.currentTarget;
        const field = input.dataset.notificationField;
        const value = input.checked;
        const switchControl = input.closest(".ut-settings-switch");

        if (switchControl) {
            switchControl.classList.add("is-saving");
        }

        try {
            const result = await jsonrpc("/my/settings/notifications", {
                field: field,
                value: value,
            });

            if (!result || !result.success) {
                throw new Error((result && result.message) || "Notification update failed");
            }

            const values = result.values || {};
            this.el.querySelectorAll("[data-notification-field]").forEach((control) => {
                if (Object.prototype.hasOwnProperty.call(values, control.dataset.notificationField)) {
                    control.checked = Boolean(values[control.dataset.notificationField]);
                }
            });
        } catch (error) {
            input.checked = !value;
            console.error("[UniTrade] Settings notification toggle:", error);
        } finally {
            if (switchControl) {
                switchControl.classList.remove("is-saving");
            }
        }
    },
});
