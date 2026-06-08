/** @odoo-module **/

const NOTIFICATION_SELECTOR = '.ut-dash-navbar a.ut-dash-nav-round[href="/unitrade/seller/notifications"]';
const ENHANCED_ATTR = "data-seller-notification-enhanced";
const UNREAD_COUNT_URL = "/unitrade/seller/notifications/unread_count";
const RECENT_URL = "/unitrade/seller/notifications/recent";
const READ_ALL_URL = "/unitrade/seller/notifications/read_all";
const CENTER_URL = "/unitrade/seller/notifications";
const STARTED_FLAG = "__unitradeSellerNotificationDropdownStarted";

async function jsonPost(url, params = {}) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params,
        }),
        credentials: "same-origin",
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status} on ${url}`);
    }
    const data = await response.json();
    if (data && data.error) {
        const message =
            (data.error.data && data.error.data.message) ||
            data.error.message ||
            "RPC error";
        throw new Error(message);
    }
    return data ? data.result : undefined;
}

function badgeText(count) {
    if (!count || count <= 0) {
        return "";
    }
    return count > 99 ? "99+" : String(count);
}

function parseDate(value) {
    if (!value) {
        return null;
    }
    const normalized = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
}

function timeLabel(value) {
    const date = parseDate(value);
    if (!date) {
        return value || "";
    }
    const diffMinutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
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

function groupLabel(value) {
    const date = parseDate(value);
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

function itemIcon(category) {
    const icons = {
        order: "fa-shopping-bag",
        payment: "fa-credit-card",
        review: "fa-star",
        chat: "fa-commenting-o",
        seller: "fa-shopping-basket",
        account: "fa-user",
        system: "fa-bell",
    };
    return icons[category] || "fa-bell";
}

function ensureBadge(anchor) {
    let badge = anchor.querySelector(".ut-dash-navbar-dot");
    if (!badge) {
        badge = document.createElement("span");
        badge.className = "ut-dash-navbar-dot";
        anchor.appendChild(badge);
    }
    return badge;
}

function updateBadge(anchor, count) {
    const badge = ensureBadge(anchor);
    const text = badgeText(count);
    badge.textContent = text;
    badge.hidden = !text;
}

function createPanel() {
    const panel = document.createElement("div");
    panel.className = "ut-seller-notification-panel";
    panel.hidden = true;
    panel.innerHTML = `
        <div class="ut-seller-notification-head">
            <div>
                <strong>Notifikasi Penjual</strong>
                <span>Aktivitas toko terbaru</span>
            </div>
            <a href="${CENTER_URL}" aria-label="Buka halaman notifikasi penjual">
                <i class="fa fa-external-link"></i>
            </a>
        </div>
        <div class="ut-seller-notification-tabs">
            <button type="button" data-filter="all" class="is-active">Semua</button>
            <button type="button" data-filter="unread">Belum dibaca</button>
            <button type="button" data-action="read-all">Tandai semua</button>
        </div>
        <div class="ut-seller-notification-list" role="list"></div>
        <a class="ut-seller-notification-footer" href="${CENTER_URL}">Lihat semua notifikasi</a>
    `;
    return panel;
}

function emptyMarkup(message) {
    return `
        <div class="ut-seller-notification-empty">
            <strong>Belum ada notifikasi</strong>
            <span>${message}</span>
        </div>
    `;
}

function renderList(listEl, records, filter) {
    const visible = filter === "unread" ? records.filter((record) => !record.is_read) : records;
    if (!visible.length) {
        listEl.innerHTML = emptyMarkup(
            filter === "unread"
                ? "Semua notifikasi penjual sudah dibaca."
                : "Pesanan, ulasan, refund, dan chat penjual akan muncul di sini."
        );
        return;
    }

    let lastGroup = "";
    listEl.innerHTML = visible
        .map((record) => {
            const group = groupLabel(record.create_date);
            const header = group !== lastGroup
                ? `<div class="ut-seller-notification-group">${group}</div>`
                : "";
            lastGroup = group;
            const unreadClass = record.is_read ? "" : " is-unread";
            const title = escapeHtml(record.title || "Notifikasi UniTrade");
            const message = escapeHtml(record.message || "");
            return `
                ${header}
                <button type="button"
                        class="ut-seller-notification-item${unreadClass}"
                        data-notification-id="${record.id}"
                        data-action-url="${escapeAttr(record.action_url || CENTER_URL)}">
                    <span class="ut-seller-notification-icon">
                        <i class="fa ${itemIcon(record.category)}"></i>
                        ${record.is_read ? "" : '<span class="ut-seller-notification-dot"></span>'}
                    </span>
                    <span class="ut-seller-notification-body">
                        <strong>${title}</strong>
                        ${message ? `<span>${message}</span>` : ""}
                        <small>${escapeHtml(timeLabel(record.create_date))}</small>
                    </span>
                </button>
            `;
        })
        .join("");
}

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
}

function enhanceNotificationAnchor(anchor) {
    if (!anchor || !anchor.matches(NOTIFICATION_SELECTOR) || anchor.closest(".ut-seller-notification-panel")) {
        return;
    }
    if (anchor.getAttribute(ENHANCED_ATTR) === "1") {
        return;
    }
    if (anchor.closest(".ut-seller-notification-wrapper")) {
        return;
    }
    anchor.setAttribute(ENHANCED_ATTR, "1");
    anchor.classList.add("ut-seller-notification-trigger");

    const wrapper = document.createElement("div");
    wrapper.className = "ut-seller-notification-wrapper";
    anchor.parentNode.insertBefore(wrapper, anchor);
    wrapper.appendChild(anchor);

    const panel = createPanel();
    wrapper.appendChild(panel);

    const listEl = panel.querySelector(".ut-seller-notification-list");
    const filterButtons = Array.from(panel.querySelectorAll("[data-filter]"));
    const readAllButton = panel.querySelector("[data-action='read-all']");
    let records = [];
    let filter = "all";
    let closeTimer = null;
    let openedByClick = false;
    let countInFlight = null;
    let recentInFlight = null;

    const close = () => {
        panel.hidden = true;
        anchor.setAttribute("aria-expanded", "false");
        openedByClick = false;
    };
    const clearCloseTimer = () => {
        if (closeTimer !== null) {
            window.clearTimeout(closeTimer);
            closeTimer = null;
        }
    };
    const scheduleClose = () => {
        if (openedByClick) {
            return;
        }
        clearCloseTimer();
        closeTimer = window.setTimeout(close, 160);
    };
    const setFilter = (nextFilter) => {
        filter = nextFilter;
        filterButtons.forEach((button) => {
            button.classList.toggle("is-active", button.dataset.filter === filter);
        });
        renderList(listEl, records, filter);
    };
    const refreshCount = async () => {
        if (countInFlight) {
            return countInFlight;
        }
        countInFlight = (async () => {
            try {
                const result = await jsonPost(UNREAD_COUNT_URL);
                updateBadge(anchor, result && typeof result.count === "number" ? result.count : 0);
            } catch (error) {
                updateBadge(anchor, 0);
            } finally {
                countInFlight = null;
            }
        })();
        return countInFlight;
    };
    const loadRecent = async () => {
        if (recentInFlight) {
            return recentInFlight;
        }
        try {
            listEl.innerHTML = '<div class="ut-seller-notification-empty">Memuat notifikasi...</div>';
            recentInFlight = (async () => {
                try {
                    records = await jsonPost(RECENT_URL) || [];
                    renderList(listEl, records, filter);
                } catch (error) {
                    records = [];
                    listEl.innerHTML = emptyMarkup("Notifikasi penjual belum bisa dimuat.");
                } finally {
                    recentInFlight = null;
                }
            })();
            return recentInFlight;
        } catch (error) {
            recentInFlight = null;
            throw error;
        }
    };
    const open = async () => {
        clearCloseTimer();
        if (!panel.hidden) {
            return;
        }
        panel.hidden = false;
        anchor.setAttribute("aria-expanded", "true");
        await Promise.all([refreshCount(), loadRecent()]);
    };

    anchor.setAttribute("aria-haspopup", "dialog");
    anchor.setAttribute("aria-expanded", "false");

    wrapper.addEventListener("mouseenter", () => {
        openedByClick = false;
        open();
    });
    wrapper.addEventListener("mouseleave", scheduleClose);
    anchor.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        clearCloseTimer();
        if (!panel.hidden && openedByClick) {
            close();
            return;
        }
        openedByClick = true;
        open();
    });
    filterButtons.forEach((button) => {
        button.addEventListener("click", () => setFilter(button.dataset.filter || "all"));
    });
    readAllButton.addEventListener("click", async () => {
        try {
            await jsonPost(READ_ALL_URL);
        } catch (error) {
            // Keep the dropdown usable even if the backend is briefly unavailable.
        }
        await refreshCount();
        await loadRecent();
    });
    listEl.addEventListener("click", async (ev) => {
        const item = ev.target.closest(".ut-seller-notification-item");
        if (!item) {
            return;
        }
        const id = Number(item.dataset.notificationId);
        if (id) {
            try {
                await jsonPost(`/my/notifications/${id}/read`);
            } catch (error) {
                // Navigation is still useful when mark-read fails.
            }
        }
        window.location.href = item.dataset.actionUrl || CENTER_URL;
    });
    document.addEventListener("click", (ev) => {
        if (!panel.hidden && !wrapper.contains(ev.target)) {
            close();
        }
    });
    document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape" && !panel.hidden) {
            close();
        }
    });
}

function initializeSellerNotificationDropdowns() {
    document.querySelectorAll(NOTIFICATION_SELECTOR).forEach(enhanceNotificationAnchor);
}

function hasEnhancedNotificationDropdown() {
    return Boolean(document.querySelector(`${NOTIFICATION_SELECTOR}[${ENHANCED_ATTR}="1"]`));
}

function startObserver() {
    if (window[STARTED_FLAG]) {
        return;
    }
    window[STARTED_FLAG] = true;
    initializeSellerNotificationDropdowns();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver, { once: true });
} else {
    startObserver();
}
