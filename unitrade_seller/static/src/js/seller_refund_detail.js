/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";
import { mountSellerApp } from "./seller_mount";

function parsePayload(dataset) {
    try {
        return JSON.parse(dataset.refundDetailPayload || "{}");
    } catch (error) {
        console.error("[UniTrade] Seller refund detail payload:", error);
        return {};
    }
}

export class SellerRefundDetail extends Component {
    static template = "unitrade_seller.SellerRefundDetail";
    static props = {
        payload: Object,
    };

    setup() {
        const payload = this.props.payload || {};
        this.state = useState({
            ready: false,
            sidebarOpen: readSellerSidebarOpen(),
            payload,
            sellerNote: (payload.refund && payload.refund.seller_note) || "",
            decisionLoading: "",
            decisionError: "",
            toast: "",
            previewEvidence: null,
        });

        onMounted(() => {
            window.setTimeout(() => {
                this.state.ready = true;
            }, 120);
        });
        onWillUnmount(() => {
            window.clearTimeout(this.toastTimer);
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

    get refund() {
        return this.payload.refund || {};
    }

    get order() {
        return this.payload.order || {};
    }

    get buyer() {
        return this.payload.buyer || {};
    }

    get product() {
        return this.payload.product || {};
    }

    get summary() {
        return this.payload.summary || {};
    }

    get evidence() {
        return this.payload.evidence || [];
    }

    get timeline() {
        return this.payload.timeline || [];
    }

    get sidebarActiveKey() {
        return "refund";
    }

    get sidebarClass() {
        return "ut-refund-detail-sidebar";
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

    get canDecide() {
        return Boolean(this.refund.can_decide) && !this.state.decisionLoading;
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    statusPillClass() {
        return `ut-refund-detail-status ut-refund-detail-status-${this.refund.status_key || "draft"}`;
    }

    timelineStepClass(step) {
        const classes = ["ut-refund-detail-step"];
        if (step.done) {
            classes.push("is-done");
        }
        if (step.active) {
            classes.push("is-active");
        }
        if (step.failed) {
            classes.push("is-failed");
        }
        return classes.join(" ");
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

    onSellerNoteInput(ev) {
        this.state.sellerNote = ev.target.value || "";
        this.state.decisionError = "";
    }

    openEvidencePreview(evidence) {
        this.state.previewEvidence = evidence;
    }

    closeEvidencePreview() {
        this.state.previewEvidence = null;
    }

    showToast(message) {
        this.state.toast = message || "Perubahan tersimpan.";
        window.clearTimeout(this.toastTimer);
        this.toastTimer = window.setTimeout(() => {
            this.state.toast = "";
        }, 3200);
    }

    async decide(decision) {
        if (!this.canDecide) {
            return;
        }
        const note = String(this.state.sellerNote || "").trim();
        if (decision === "reject" && !note) {
            this.state.decisionError = "Catatan Seller wajib diisi sebelum menolak refund.";
            return;
        }
        this.state.decisionLoading = decision;
        this.state.decisionError = "";
        try {
            const result = await jsonrpc(this.refund.decision_url, {
                decision,
                seller_note: note,
            });
            if (!result || result.success === false) {
                throw new Error((result && result.message) || "Keputusan refund belum bisa diproses.");
            }
            this.state.payload = result.payload || this.payload;
            this.state.sellerNote = (this.state.payload.refund && this.state.payload.refund.seller_note) || note;
            this.showToast(result.message || "Keputusan refund tersimpan.");
        } catch (error) {
            this.state.decisionError = error.message || "Keputusan refund belum bisa diproses.";
        } finally {
            this.state.decisionLoading = "";
        }
    }

    approveRefund() {
        return this.decide("approve");
    }

    rejectRefund() {
        return this.decide("reject");
    }
}

publicWidget.registry.UnitradeSellerRefundDetail = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-refund-detail-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const payload = parsePayload(this.el.dataset);
        await mountSellerApp(this, SellerRefundDetail, { payload }, templates, "Seller refund detail");
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
