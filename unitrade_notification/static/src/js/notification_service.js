/** @odoo-module **/

/**
 * Notification service for the UniTrade `unitrade.notification` system.
 *
 * Implements task 13.1 of the unitrade-notification-system spec:
 *  - Thin wrapper around the JSON controllers exposed under `/my/notifications/*`
 *    (registered in tasks 11.2 and 11.3).
 *  - Provides a polling timer abstraction for the OWL `Notification_Bell`
 *    component (task 13.2). Requirement 4.6 mandates a 60-second poll cycle
 *    on `/my/notifications/unread_count`.
 *
 * The module is intentionally framework-agnostic: it does not depend on
 * `useService` / OWL hooks so it can be reused by both the bell component and
 * unit tests. RPC errors are surfaced as `console.warn` (the JS equivalent of
 * Odoo's `_logger.warning`) and degrade gracefully to safe default values so
 * the navbar bell never breaks the parent page.
 */

const DEFAULT_POLL_INTERVAL_MS = 60000;

let _pollHandle = null;
let _pollInFlight = null;
let _unreadCountInFlight = null;
let _recentInFlight = null;

/**
 * POST a JSON-RPC envelope to an Odoo `type='json'` controller.
 * Odoo wraps the controller return value inside `{ result }` and reports
 * server errors inside `{ error }`; this helper unwraps both.
 *
 * @param {string} url   absolute path on the same origin (e.g. `/my/notifications/recent`)
 * @param {Object} [params]  payload forwarded to the controller as kwargs
 * @returns {Promise<*>} the unwrapped `result` value
 */
async function _jsonPost(url, params = {}) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: params,
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

export const notificationService = {
    /**
     * Fetch the unread badge counter. Falls back to 0 on any error so the
     * navbar bell stays usable even when the user is logged out or the
     * backend is briefly unreachable.
     */
    async fetchUnreadCount() {
        if (_unreadCountInFlight) {
            return _unreadCountInFlight;
        }
        _unreadCountInFlight = (async () => {
            try {
                const res = await _jsonPost("/my/notifications/unread_count");
                return res && typeof res.count === "number" ? res.count : 0;
            } catch (err) {
                console.warn("[unitrade_notification] fetchUnreadCount failed:", err);
                return 0;
            } finally {
                _unreadCountInFlight = null;
            }
        })();
        return _unreadCountInFlight;
    },

    /**
     * Fetch the latest 5 notifications used by the bell dropdown.
     * Always returns an array so the consumer can iterate without guards.
     */
    async fetchRecent() {
        if (_recentInFlight) {
            return _recentInFlight;
        }
        _recentInFlight = (async () => {
            try {
                const res = await _jsonPost("/my/notifications/recent");
                return Array.isArray(res) ? res : [];
            } catch (err) {
                console.warn("[unitrade_notification] fetchRecent failed:", err);
                return [];
            } finally {
                _recentInFlight = null;
            }
        })();
        return _recentInFlight;
    },

    /**
     * Mark a single notification as read. Returns `null` on failure so the
     * caller can keep navigating to `action_url` without throwing.
     */
    async markRead(id) {
        try {
            return await _jsonPost(`/my/notifications/${id}/read`);
        } catch (err) {
            console.warn("[unitrade_notification] markRead failed:", err);
            return null;
        }
    },

    /**
     * Mark every unread notification of the current user as read.
     */
    async markAllRead() {
        try {
            return await _jsonPost("/my/notifications/read_all");
        } catch (err) {
            console.warn("[unitrade_notification] markAllRead failed:", err);
            return null;
        }
    },

    /**
     * Start polling `callback` at the given interval (default 60 000 ms per
     * Requirement 4.6). Any prior timer started via this service is cleared
     * first so calling `startPolling` repeatedly is safe.
     *
     * @param {Function} callback   invoked on every tick
     * @param {number} [intervalMs] polling interval in milliseconds
     * @returns {number} the underlying interval handle
     */
    startPolling(callback, intervalMs = DEFAULT_POLL_INTERVAL_MS) {
        this.stopPolling();
        _pollHandle = window.setInterval(() => {
            if (_pollInFlight) {
                return;
            }
            _pollInFlight = Promise.resolve(callback())
                .catch((err) => console.warn("[unitrade_notification] poll failed:", err))
                .finally(() => {
                    _pollInFlight = null;
                });
        }, intervalMs);
        return _pollHandle;
    },

    /**
     * Stop the active polling timer, if any. No-op when polling is inactive.
     */
    stopPolling() {
        if (_pollHandle !== null) {
            window.clearInterval(_pollHandle);
            _pollHandle = null;
        }
        _pollInFlight = null;
    },
};

/**
 * Public constant exposed so the smoke test in task 16.2 can assert the
 * configured polling interval equals 60 000 ms (Requirement 4.6).
 */
export const NOTIFICATION_POLL_INTERVAL_MS = DEFAULT_POLL_INTERVAL_MS;
