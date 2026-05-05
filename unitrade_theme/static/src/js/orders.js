/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";

function parseCounts(value) {
    try {
        return JSON.parse(value || "{}");
    } catch (error) {
        return {};
    }
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
            { key: "done", label: "Selesai" },
            { key: "cancel", label: "Dibatalkan" },
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
