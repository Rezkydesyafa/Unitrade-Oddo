/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";
import { formatHandoffFileSize, validateHandoffImageFile } from "./seller_handoff_upload";
import { mountSellerApp } from "./seller_mount";

function parsePayload(dataset) {
    try {
        return JSON.parse(dataset.orderDetailPayload || "{}");
    } catch (error) {
        console.error("[UniTrade] Seller order detail payload:", error);
        return {};
    }
}

export class SellerOrderDetail extends Component {
    static template = "unitrade_seller.SellerOrderDetail";
    static props = {
        payload: Object,
    };

    setup() {
        this.handoffFileInputRef = useRef("handoffFileInput");
        this.state = useState({
            ready: false,
            sidebarOpen: readSellerSidebarOpen(),
            handoffOpen: false,
            handoffDragActive: false,
            handoffFileName: "",
            handoffFileSize: "",
            handoffPreviewUrl: "",
            handoffError: "",
            evidencePreview: null,
            payload: this.props.payload || {},
        });

        onMounted(() => {
            window.setTimeout(() => {
                this.state.ready = true;
            }, 120);
        });
        onWillUnmount(() => this.resetHandoffUpload());
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

    get order() {
        return this.payload.order || {};
    }

    get timeline() {
        return this.payload.timeline || [];
    }

    get sidebarActiveKey() {
        return "orders";
    }

    get sidebarClass() {
        return "ut-order-detail-sidebar";
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

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    statusClass(status) {
        return `ut-orders-status ut-orders-status-${status || "new"}`;
    }

    stepClass(step) {
        const classes = ["ut-order-detail-step"];
        if (step.done) {
            classes.push("is-done");
        }
        if (step.active) {
            classes.push("is-active");
        }
        return classes.join(" ");
    }

    lineKey(line) {
        return line.id || `${line.product_name || "line"}-${line.subtotal_label || ""}`;
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

    openHandoff() {
        this.resetHandoffUpload();
        this.state.handoffOpen = true;
    }

    closeHandoff() {
        this.state.handoffOpen = false;
        this.resetHandoffUpload();
    }

    resetHandoffUpload() {
        if (this.state.handoffPreviewUrl) {
            URL.revokeObjectURL(this.state.handoffPreviewUrl);
        }
        this.state.handoffDragActive = false;
        this.state.handoffFileName = "";
        this.state.handoffFileSize = "";
        this.state.handoffPreviewUrl = "";
        this.state.handoffError = "";
        const input = this.handoffFileInputRef.el;
        if (input) {
            input.value = "";
        }
    }

    openHandoffFilePicker() {
        const input = this.handoffFileInputRef.el;
        if (input) {
            input.click();
        }
    }

    validateHandoffFile(file) {
        return validateHandoffImageFile(file);
    }

    setHandoffFile(file) {
        const error = this.validateHandoffFile(file);
        if (error) {
            this.resetHandoffUpload();
            this.state.handoffError = error;
            return;
        }
        if (this.state.handoffPreviewUrl) {
            URL.revokeObjectURL(this.state.handoffPreviewUrl);
        }
        const input = this.handoffFileInputRef.el;
        if (input && window.DataTransfer) {
            const transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;
        }
        this.state.handoffFileName = file.name || "bukti-penyerahan.jpg";
        this.state.handoffFileSize = formatHandoffFileSize(file.size);
        this.state.handoffPreviewUrl = URL.createObjectURL(file);
        this.state.handoffError = "";
    }

    onHandoffFileChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        this.setHandoffFile(file);
    }

    onHandoffDragEnter(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.handoffDragActive = true;
    }

    onHandoffDragOver(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.handoffDragActive = true;
    }

    onHandoffDragLeave(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.handoffDragActive = false;
        }
    }

    onHandoffDrop(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.handoffDragActive = false;
        const file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
        this.setHandoffFile(file);
    }

    clearHandoffFile(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        this.resetHandoffUpload();
    }

    openEvidencePreview(src, title, caption = "") {
        if (!src) {
            return;
        }
        this.state.evidencePreview = {
            src,
            title: title || "Bukti Pesanan",
            caption,
        };
    }

    closeEvidencePreview() {
        this.state.evidencePreview = null;
    }
}

publicWidget.registry.UnitradeSellerOrderDetail = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-order-detail-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const payload = parsePayload(this.el.dataset);
        await mountSellerApp(this, SellerOrderDetail, { payload }, templates, "Seller order detail");
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
