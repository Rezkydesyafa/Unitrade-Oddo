/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";
import { mountSellerApp } from "./seller_mount";

function fallbackPayload(dataset, parsed) {
    if (parsed && parsed.summary) {
        return parsed;
    }
    return {
        seller: {
            name: dataset.sellerName || "Penjual UniTrade",
            avatar_url: dataset.sellerAvatarUrl || "/web/static/img/user_menu_avatar.png",
            profile_url: dataset.sellerProfileUrl || "/unitrade/seller/dashboard",
        },
        stats: {
            notification_count: Number(dataset.notificationCount || 0),
            unread_chat_count: Number(dataset.unreadChatCount || 0),
        },
        summary: {
            available_balance_label: "Rp 0",
            held_balance_label: "Rp 0",
            month_revenue_label: "Rp 0",
            account_label: "Belum ada rekening",
            account_ready: false,
            settings_url: "/unitrade/seller/settings#payout-settings",
            can_request_payout: false,
        },
        countdown: {
            target_at: "",
            remaining_label: "Tidak ada dana tertahan",
            progress: 100,
        },
        verification: { has_data: false, steps: [] },
        ready_ledgers: [],
        history: [],
        bank_options: [{ value: "", label: "Pilih bank" }],
        account_form: {
            bank_name: "",
            account_number: "",
            account_name: "",
        },
        account_save_url: "/unitrade/seller/payout/account/save",
        request_url: "/unitrade/seller/payout/request",
        data_url: "/unitrade/seller/payouts/data",
    };
}

function accountFormFromPayload(payload = {}) {
    const account = payload.account_form || {};
    return {
        bankName: account.bank_name || "",
        accountNumber: account.account_number || "",
        accountName: account.account_name || "",
    };
}

function parseServerDate(value) {
    if (!value) {
        return null;
    }
    const normalized = String(value).replace(" ", "T");
    const date = new Date(`${normalized.endsWith("Z") ? normalized : `${normalized}Z`}`);
    return Number.isNaN(date.getTime()) ? null : date;
}

function remainingLabel(targetAt) {
    const target = parseServerDate(targetAt);
    if (!target) {
        return "";
    }
    const totalMinutes = Math.max(0, Math.floor((target.getTime() - Date.now()) / 60000));
    const days = Math.floor(totalMinutes / 1440);
    const hours = Math.floor((totalMinutes % 1440) / 60);
    const minutes = totalMinutes % 60;
    const parts = [];
    if (days) {
        parts.push(`${days} Hari`);
    }
    if (hours || days) {
        parts.push(`${hours} Jam`);
    }
    parts.push(`${minutes} Menit`);
    return parts.join(" ");
}

export class SellerPayouts extends Component {
    static template = "unitrade_seller.SellerPayouts";
    static props = {
        payload: Object,
    };

    setup() {
        const payload = this.props.payload || {};
        this.countdownTimer = null;
        this.onAccountKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.accountModalOpen) {
                this.closeAccountModal(ev);
            }
        };
        this.state = useState({
            ready: false,
            loading: false,
            error: "",
            success: "",
            actionLedgerId: 0,
            payload,
            sidebarOpen: readSellerSidebarOpen(),
            countdownLabel: remainingLabel(payload.countdown && payload.countdown.target_at) || (payload.countdown && payload.countdown.remaining_label) || "",
            accountModalOpen: false,
            accountSaving: false,
            accountError: "",
            accountForm: accountFormFromPayload(payload),
        });

        onMounted(() => {
            document.addEventListener("keydown", this.onAccountKeydown);
            this.countdownTimer = window.setInterval(() => this.refreshCountdown(), 60000);
            window.setTimeout(() => {
                this.state.ready = true;
                this.refreshCountdown();
            }, 180);
        });
        onWillUnmount(() => {
            document.removeEventListener("keydown", this.onAccountKeydown);
            window.clearInterval(this.countdownTimer);
            document.body.classList.remove("ut-payout-account-modal-open");
        });
    }

    get payload() {
        return this.state.payload || {};
    }

    get seller() {
        return this.payload.seller || {};
    }

    get stats() {
        return this.payload.stats || {};
    }

    get summary() {
        return this.payload.summary || {};
    }

    get countdown() {
        return this.payload.countdown || {};
    }

    get verification() {
        return this.payload.verification || {};
    }

    get readyLedgers() {
        return this.payload.ready_ledgers || [];
    }

    get history() {
        return this.payload.history || [];
    }

    get bankOptions() {
        return this.payload.bank_options || [];
    }

    get sidebarActiveKey() {
        return "payout";
    }

    get sidebarClass() {
        return "ut-payout-sidebar";
    }

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.stats);
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get countdownProgressStyle() {
        const progress = Math.max(0, Math.min(100, Number(this.countdown.progress || 0)));
        return `width: ${progress}%`;
    }

    get primaryPayoutDisabled() {
        return this.state.loading || !this.summary.can_request_payout;
    }

    refreshCountdown() {
        const label = remainingLabel(this.countdown.target_at);
        this.state.countdownLabel = label || this.countdown.remaining_label || "Tidak ada dana tertahan";
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
        writeSellerSidebarOpen(this.state.sidebarOpen);
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
        writeSellerSidebarOpen(false);
    }

    onSidebarNavClick() {
        if (window.innerWidth <= 1024) {
            this.closeSidebar();
        }
    }

    stepClass(step) {
        return step.done ? "ut-payout-timeline-step is-done" : "ut-payout-timeline-step";
    }

    historyStatusClass(item) {
        return `ut-payout-history-status ${item.status_class || "is-processing"}`;
    }

    applyPayoutPayload(payload) {
        if (!payload || payload.success === false) {
            return;
        }
        this.state.payload = payload;
        if (!this.state.accountModalOpen) {
            this.state.accountForm = accountFormFromPayload(payload);
        }
        this.refreshCountdown();
    }

    openAccountModal(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.state.accountForm = accountFormFromPayload(this.payload);
        this.state.accountError = "";
        this.state.error = "";
        this.state.success = "";
        this.state.accountModalOpen = true;
        document.body.classList.add("ut-payout-account-modal-open");
    }

    closeAccountModal(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (this.state.accountSaving) {
            return;
        }
        this.state.accountModalOpen = false;
        this.state.accountError = "";
        document.body.classList.remove("ut-payout-account-modal-open");
    }

    setAccountField(field, ev) {
        this.state.accountForm[field] = ev.target.value;
        this.state.accountError = "";
        this.state.error = "";
        this.state.success = "";
    }

    async saveAccount(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (this.state.accountSaving) {
            return;
        }
        const form = this.state.accountForm || {};
        if (!form.bankName) {
            this.state.accountError = "Pilih bank atau e-wallet terlebih dahulu.";
            return;
        }
        if (!String(form.accountNumber || "").trim()) {
            this.state.accountError = "Nomor rekening wajib diisi.";
            return;
        }
        if (!String(form.accountName || "").trim()) {
            this.state.accountError = "Nama pemilik rekening wajib diisi.";
            return;
        }
        this.state.accountSaving = true;
        this.state.accountError = "";
        this.state.error = "";
        this.state.success = "";
        try {
            const result = await jsonrpc(this.payload.account_save_url || "/unitrade/seller/payout/account/save", {
                bank_name: form.bankName,
                account_number: String(form.accountNumber || "").trim(),
                account_name: String(form.accountName || "").trim(),
            });
            if (!result || result.success === false) {
                throw new Error((result && result.message) || "Rekening belum bisa disimpan.");
            }
            if (result.payout_payload) {
                this.applyPayoutPayload(result.payout_payload);
            } else {
                await this.reload();
            }
            this.state.success = result.message || "Rekening pencairan berhasil disimpan.";
            this.state.accountModalOpen = false;
            document.body.classList.remove("ut-payout-account-modal-open");
        } catch (error) {
            this.state.accountError = error.message || "Rekening belum bisa disimpan.";
        } finally {
            this.state.accountSaving = false;
        }
    }

    async reload() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const payload = await jsonrpc(this.payload.data_url || "/unitrade/seller/payouts/data", {});
            if (!payload || payload.success === false) {
                throw new Error((payload && payload.message) || "Data pencairan belum bisa dimuat.");
            }
            this.applyPayoutPayload(payload);
        } catch (error) {
            this.state.error = error.message || "Data pencairan belum bisa dimuat.";
        } finally {
            this.state.loading = false;
        }
    }

    async requestPayout(ledgerId = 0) {
        if (!this.summary.account_ready) {
            this.openAccountModal();
            return;
        }
        if (this.state.loading || (ledgerId && this.state.actionLedgerId)) {
            return;
        }
        this.state.loading = !ledgerId;
        this.state.actionLedgerId = Number(ledgerId || 0);
        this.state.error = "";
        this.state.success = "";
        try {
            const result = await jsonrpc(this.payload.request_url || "/unitrade/seller/payout/request", {
                ledger_id: ledgerId || false,
            });
            if (!result || result.success === false) {
                throw new Error((result && result.message) || "Permintaan pencairan belum bisa diproses.");
            }
            this.state.success = result.message || "Permintaan pencairan berhasil dikirim.";
            if (result.payout_payload) {
                this.applyPayoutPayload(result.payout_payload);
            } else {
                await this.reload();
            }
        } catch (error) {
            this.state.error = error.message || "Permintaan pencairan belum bisa diproses.";
        } finally {
            this.state.loading = false;
            this.state.actionLedgerId = 0;
        }
    }
}

publicWidget.registry.UnitradeSellerPayouts = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-payouts-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        let parsed = {};
        try {
            parsed = JSON.parse(this.el.dataset.sellerPayoutPayload || "{}");
        } catch (error) {
            parsed = {};
        }
        const payload = fallbackPayload(this.el.dataset, parsed);
        await mountSellerApp(this, SellerPayouts, { payload }, templates, "Seller payouts");
        await superPromise;
    },

    destroy() {
        if (this.component) {
            this.component.destroy();
        }
        return this._super ? this._super.apply(this, arguments) : undefined;
    },
});
