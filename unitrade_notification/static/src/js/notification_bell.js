/** @odoo-module **/

/**
 * NotificationBell OWL component for the UniTrade `unitrade.notification`
 * system (task 13.2 of the unitrade-notification-system spec).
 *
 * Responsibilities (Requirements 4.1 - 4.5):
 *  - Render an unread-count badge in the website navbar.
 *  - Fetch the unread count on mount and refresh it every 60 seconds via
 *    `notificationService` (task 13.1, Requirement 4.6).
 *  - Open a dropdown of the last 5 notifications on click (lazy loaded).
 *  - Mark a notification as read when clicked, then redirect to its
 *    `action_url` (or `/my/notifications` if absent).
 *  - Provide a "mark all as read" action.
 *
 * Mounting strategy:
 *  - Registered under `public_components` so the `website` module mounts the
 *    component on every public page (including `/my/...`). This avoids
 *    creating a backend service and keeps the bell available to portal users.
 *  - The XML template id (registered in task 13.3) MUST equal
 *    `unitrade_notification.NotificationBell` to match `static template`.
 */

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    notificationService,
    NOTIFICATION_POLL_INTERVAL_MS,
} from "./notification_service";

export class NotificationBell extends Component {
    static template = "unitrade_notification.NotificationBell";
    static props = {};

    setup() {
        this.state = useState({
            count: 0,
            badgeText: "",
            isOpen: false,
            isLoading: false,
            openedByClick: false,
            activeFilter: "all",
            recent: [],
        });
        this.root = useRef("root");
        this.closeTimer = null;
        this.onDocumentClick = this.onDocumentClick.bind(this);
        this.onKeyDown = this.onKeyDown.bind(this);
        this.onExternalCount = this.onExternalCount.bind(this);

        onMounted(async () => {
            this.root.el?.closest(".ut-notification-host")?.classList.add("ut-is-mounted");
            await this.refreshCount();
            // `startPolling` clears any prior timer first, so this is safe
            // even if the component is remounted on the same page.
            notificationService.startPolling(
                () => this.refreshCount(),
                NOTIFICATION_POLL_INTERVAL_MS
            );
            document.addEventListener("click", this.onDocumentClick);
            document.addEventListener("keydown", this.onKeyDown);
            window.addEventListener("unitrade:notifications-count", this.onExternalCount);
        });

        onWillUnmount(() => {
            this.root.el?.closest(".ut-notification-host")?.classList.remove("ut-is-mounted");
            notificationService.stopPolling();
            this.clearCloseTimer();
            document.removeEventListener("click", this.onDocumentClick);
            document.removeEventListener("keydown", this.onKeyDown);
            window.removeEventListener("unitrade:notifications-count", this.onExternalCount);
        });
    }

    setCount(count) {
        this.state.count = count;
        this.state.badgeText = NotificationBell.computeBadgeText(count);
    }

    onExternalCount(ev) {
        const count = Number(ev.detail && ev.detail.count);
        if (Number.isFinite(count)) {
            this.setCount(Math.max(0, count));
        }
    }

    /**
     * Compute the badge display text per Property 8:
     *   count <= 0    -> ""
     *   1 <= count <= 99 -> String(count)
     *   count > 99    -> "99+"
     *
     * Exposed as a static method so task 13.5 can property-test it directly
     * without instantiating the component.
     *
     * @param {number} count unread count returned by the backend
     * @returns {string} badge label
     */
    static computeBadgeText(count) {
        if (!count || count <= 0) {
            return "";
        }
        if (count > 99) {
            return "99+";
        }
        return String(count);
    }

    /**
     * Refresh the unread count from the backend and recompute the badge.
     * Errors are absorbed inside `notificationService.fetchUnreadCount`,
     * which falls back to 0 to keep the navbar usable.
     */
    async refreshCount() {
        const count = await notificationService.fetchUnreadCount();
        this.setCount(count);
    }

    /**
     * Toggle the dropdown. Recent notifications are lazy-loaded on every
     * open so the user always sees fresh data without paying the cost on
     * page load.
     */
    async onButtonClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.clearCloseTimer();
        if (this.state.isOpen && this.state.openedByClick) {
            this.close();
            return;
        }
        this.state.openedByClick = true;
        await this.open();
    }

    async openFromHover() {
        this.clearCloseTimer();
        if (this.state.isOpen) {
            return;
        }
        this.state.openedByClick = false;
        await this.open();
    }

    async open() {
        this.state.isOpen = true;
        await this.loadRecent();
    }

    close() {
        this.state.isOpen = false;
        this.state.openedByClick = false;
    }

    scheduleClose() {
        if (this.state.openedByClick) {
            return;
        }
        this.clearCloseTimer();
        this.closeTimer = window.setTimeout(() => this.close(), 160);
    }

    clearCloseTimer() {
        if (this.closeTimer !== null) {
            window.clearTimeout(this.closeTimer);
            this.closeTimer = null;
        }
    }

    async loadRecent() {
        this.state.isLoading = true;
        const records = await notificationService.fetchRecent();
        this.state.recent = records.map((record) => this.prepareNotification(record));
        this.state.isLoading = false;
    }

    prepareNotification(record) {
        const createDate = record.create_date || "";
        return {
            ...record,
            title: record.title || "Notifikasi UniTrade",
            message: record.message || "",
            groupLabel: this.getGroupLabel(createDate),
            timeLabel: this.getTimeLabel(createDate),
        };
    }

    parseDate(value) {
        if (!value) {
            return null;
        }
        const normalized = value.includes("T") ? value : value.replace(" ", "T") + "Z";
        const date = new Date(normalized);
        return Number.isNaN(date.getTime()) ? null : date;
    }

    getGroupLabel(value) {
        const date = this.parseDate(value);
        if (!date) {
            return "Sebelumnya";
        }
        const now = new Date();
        const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const startYesterday = new Date(startToday);
        startYesterday.setDate(startYesterday.getDate() - 1);
        const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
        if (startDate.getTime() === startToday.getTime()) {
            return "Hari ini";
        }
        if (startDate.getTime() === startYesterday.getTime()) {
            return "Kemarin";
        }
        return "Sebelumnya";
    }

    getTimeLabel(value) {
        const date = this.parseDate(value);
        if (!date) {
            return value || "";
        }
        const diffMs = Math.max(0, Date.now() - date.getTime());
        const diffMinutes = Math.floor(diffMs / 60000);
        if (diffMinutes < 1) {
            return "Baru saja";
        }
        if (diffMinutes < 60) {
            return `${diffMinutes} menit lalu`;
        }
        const diffHours = Math.floor(diffMinutes / 60);
        if (diffHours < 24) {
            return `${diffHours} jam lalu`;
        }
        return date.toLocaleString("id-ID", {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    setFilter(filter) {
        this.state.activeFilter = filter;
    }

    getVisibleNotifications() {
        const visible = [];
        let lastGroup = "";
        const source =
            this.state.activeFilter === "unread"
                ? this.state.recent.filter((notif) => !notif.is_read)
                : this.state.recent;
        for (const notif of source) {
            const showGroupLabel = notif.groupLabel !== lastGroup;
            visible.push({ ...notif, showGroupLabel });
            lastGroup = notif.groupLabel;
        }
        return visible;
    }

    hasVisibleNotifications() {
        if (this.state.activeFilter === "unread") {
            return this.state.recent.some((notif) => !notif.is_read);
        }
        return this.state.recent.length > 0;
    }

    tabClass(filter) {
        const classes = ["ut-notification-tab"];
        if (this.state.activeFilter === filter) {
            classes.push("ut-is-active");
        }
        return classes.join(" ");
    }

    itemClass(notif) {
        const classes = ["ut-notification-item"];
        if (!notif.is_read) {
            classes.push("ut-is-unread");
        }
        return classes.join(" ");
    }

    onDocumentClick(ev) {
        if (!this.state.isOpen || !this.root.el) {
            return;
        }
        if (!this.root.el.contains(ev.target)) {
            this.close();
        }
    }

    onKeyDown(ev) {
        if (ev.key === "Escape" && this.state.isOpen) {
            this.close();
        }
    }

    /**
     * Click handler for an individual notification row.
     * Marks the notification as read, then navigates to its `action_url`
     * or `/my/notifications` as a fallback (Requirement 4.4).
     *
     * @param {{id: number, action_url?: string}} notif
     */
    async onClickItem(notif) {
        if (notif && notif.id) {
            await notificationService.markRead(notif.id);
        }
        const target = (notif && notif.action_url) || "/my/notifications";
        window.location = target;
    }

    /**
     * Click handler for the "Mark all as read" link in the dropdown footer.
     * Refreshes both the badge count and the recent list so the dropdown
     * reflects the new state without closing.
     */
    async onClickMarkAllRead() {
        await notificationService.markAllRead();
        await this.refreshCount();
        await this.loadRecent();
    }
}

registry
    .category("public_components")
    .add("unitrade_notification.NotificationBell", NotificationBell);
