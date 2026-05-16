/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { sellerSidebarItems } from "./seller_sidebar";

function toNumber(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
}

function payloadFromDataset(dataset, parsed) {
    if (parsed && parsed.settings) {
        return parsed;
    }
    return {
        seller: {
            name: dataset.sellerName || "Penjual UniTrade",
            avatar_url: dataset.sellerAvatarUrl || "/web/static/img/user_menu_avatar.png",
            profile_url: dataset.sellerProfileUrl || "/unitrade/seller/dashboard",
        },
        stats: {
            notification_count: toNumber(dataset.notificationCount),
            unread_chat_count: toNumber(dataset.unreadChatCount),
        },
        settings: {},
        bank_options: [],
        data_url: "/unitrade/seller/settings/data",
        update_url: "/unitrade/seller/settings/update",
        close_url: "/unitrade/seller/settings/close-store",
        delete_request_url: "/unitrade/seller/settings/request-delete",
    };
}

export class SellerSettings extends Component {
    static template = "unitrade_seller.SellerSettings";
    static props = {
        payload: Object,
    };

    setup() {
        const payload = this.props.payload || {};
        this.state = useState({
            ready: false,
            loading: true,
            savingSection: "",
            closing: false,
            requestingDelete: false,
            error: "",
            success: "",
            sidebarOpen: false,
            seller: payload.seller || {},
            stats: payload.stats || {},
            bankOptions: payload.bank_options || [],
            dataUrl: payload.data_url || "/unitrade/seller/settings/data",
            updateUrl: payload.update_url || "/unitrade/seller/settings/update",
            closeUrl: payload.close_url || "/unitrade/seller/settings/close-store",
            deleteRequestUrl: payload.delete_request_url || "/unitrade/seller/settings/request-delete",
            form: this.formFromSettings(payload.settings || {}),
        });

        onMounted(() => this.loadSettings());
    }

    get seller() {
        return this.state.seller || {};
    }

    get stats() {
        return this.state.stats || {};
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.stats);
    }

    get sidebarActiveKey() {
        return "settings";
    }

    get sidebarClass() {
        return "ut-settings-sidebar";
    }

    formFromSettings(settings) {
        return {
            storeUrlBase: settings.store_url_base || "unitrade.my.id/",
            slug: settings.slug || "",
            description: settings.description || "",
            province: settings.province || "",
            city: settings.city || "",
            addressDetail: settings.address_detail || "",
            bankName: settings.bank_name || "",
            accountNumber: settings.account_number || "",
            accountName: settings.account_name || "",
            storeActive: settings.store_active !== false,
            deleteRequested: Boolean(settings.delete_requested),
        };
    }

    applyPayload(payload) {
        this.state.seller = payload.seller || this.state.seller;
        this.state.stats = payload.stats || this.state.stats;
        this.state.bankOptions = payload.bank_options || this.state.bankOptions;
        this.state.form = this.formFromSettings(payload.settings || {});
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    setField(field, ev) {
        this.state.form[field] = ev.target.value;
        this.state.error = "";
        this.state.success = "";
    }

    setStoreActive(ev) {
        this.state.form.storeActive = Boolean(ev.target.checked);
        this.state.error = "";
        this.state.success = "";
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
    }

    onSidebarNavClick() {
        if (window.innerWidth <= 1024) {
            this.closeSidebar();
        }
    }

    async loadSettings() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc(this.state.dataUrl, {});
            if (!result.success) {
                throw new Error(result.message || "Pengaturan toko belum bisa dimuat.");
            }
            this.applyPayload(result);
        } catch (error) {
            console.error("[UniTrade] Seller settings:", error);
            this.state.error = error.message || "Pengaturan toko belum bisa dimuat.";
        } finally {
            this.state.loading = false;
            window.setTimeout(() => {
                this.state.ready = true;
            }, 160);
        }
    }

    payloadForSave() {
        const form = this.state.form;
        return {
            slug: form.slug,
            description: form.description,
            province: form.province,
            city: form.city,
            address_detail: form.addressDetail,
            bank_name: form.bankName,
            account_number: form.accountNumber,
            account_name: form.accountName,
            store_active: form.storeActive,
        };
    }

    async saveSection(section) {
        if (this.state.savingSection) {
            return;
        }
        this.state.error = "";
        this.state.success = "";
        this.state.savingSection = section;
        try {
            const result = await jsonrpc(this.state.updateUrl, this.payloadForSave());
            if (!result.success) {
                throw new Error(result.message || "Pengaturan toko belum bisa disimpan.");
            }
            this.applyPayload(result);
            this.state.success = result.message || "Pengaturan toko berhasil disimpan.";
        } catch (error) {
            console.error("[UniTrade] Seller settings save:", error);
            this.state.error = error.message || "Pengaturan toko belum bisa disimpan.";
        } finally {
            this.state.savingSection = "";
        }
    }

    async closeStore() {
        if (this.state.closing) {
            return;
        }
        if (!window.confirm("Tutup toko dan nonaktifkan seluruh produk?")) {
            return;
        }
        this.state.error = "";
        this.state.success = "";
        this.state.closing = true;
        try {
            const result = await jsonrpc(this.state.closeUrl, { confirm: "CLOSE_STORE" });
            if (!result.success) {
                throw new Error(result.message || "Toko belum bisa ditutup.");
            }
            this.state.form.storeActive = false;
            this.state.success = result.message || "Toko berhasil dinonaktifkan.";
        } catch (error) {
            console.error("[UniTrade] Seller settings close:", error);
            this.state.error = error.message || "Toko belum bisa ditutup.";
        } finally {
            this.state.closing = false;
        }
    }

    async requestDeleteSeller() {
        if (this.state.requestingDelete) {
            return;
        }
        if (!window.confirm("Ajukan penghapusan akun penjual untuk ditinjau admin? Data tidak akan dihapus permanen sekarang.")) {
            return;
        }
        this.state.error = "";
        this.state.success = "";
        this.state.requestingDelete = true;
        try {
            const result = await jsonrpc(this.state.deleteRequestUrl, { confirm: "REQUEST_SELLER_DELETE" });
            if (!result.success) {
                throw new Error(result.message || "Permintaan hapus akun belum bisa diproses.");
            }
            this.state.form.deleteRequested = true;
            this.state.success = result.message || "Permintaan hapus akun sudah dicatat.";
        } catch (error) {
            console.error("[UniTrade] Seller delete request:", error);
            this.state.error = error.message || "Permintaan hapus akun belum bisa diproses.";
        } finally {
            this.state.requestingDelete = false;
        }
    }
}

publicWidget.registry.UnitradeSellerSettings = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-settings-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        let parsed = {};
        try {
            parsed = JSON.parse(this.el.dataset.sellerSettingsPayload || "{}");
        } catch (error) {
            console.error("[UniTrade] Seller settings payload:", error);
        }
        const payload = payloadFromDataset(this.el.dataset, parsed);
        const fallbackNodes = Array.from(this.el.childNodes);
        const mountTarget = document.createElement("div");
        mountTarget.className = "ut-owl-mount-host";
        this.el.appendChild(mountTarget);
        try {
            this.component = await mount(SellerSettings, mountTarget, {
                props: { payload },
                templates,
            });
            fallbackNodes.forEach((node) => node.remove());
        } catch (error) {
            mountTarget.remove();
            console.error("[UniTrade] Seller settings mount:", error);
            this.el.classList.add("ut-owl-mount-failed");
            if (!this.el.querySelector(".ut-owl-fallback-error")) {
                const fallback = document.createElement("div");
                fallback.className = "ut-owl-fallback-error";
                fallback.textContent = "Pengaturan toko belum bisa dimuat. Muat ulang halaman setelah modul di-upgrade.";
                this.el.appendChild(fallback);
            }
        }
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
