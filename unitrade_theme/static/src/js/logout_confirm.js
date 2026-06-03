/** @odoo-module **/

import { Component, mount, onMounted, onWillUnmount, useRef, useState, xml } from "@odoo/owl";

const LOGOUT_PATH = "/web/session/logout";
const CLOSE_ANIMATION_MS = 220;

const LOGOUT_CONFIRM_TEMPLATE = xml`
    <div t-if="state.rendered" t-att-class="modalClass" role="presentation">
        <button type="button" class="ut-logout-modal-backdrop" t-on-click="close" aria-label="Tutup popup logout"></button>
        <section class="ut-logout-dialog" role="dialog" aria-modal="true" aria-labelledby="ut-logout-title" aria-describedby="ut-logout-description">
            <div class="ut-logout-icon-wrap" aria-hidden="true">
                <svg class="ut-logout-icon" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M17 10H11C9.89543 10 9 10.8954 9 12V28C9 29.1046 9.89543 30 11 30H17" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
                    <path d="M23 14L29 20L23 26" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M15 20H29" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
                </svg>
            </div>
            <h2 id="ut-logout-title" class="ut-logout-title">Keluar Dari Akun</h2>
            <p id="ut-logout-description" class="ut-logout-copy">Apakah anda yakin keluar dari UniTrade?</p>
            <div class="ut-logout-actions">
                <button t-ref="cancelButton" type="button" class="ut-logout-button ut-logout-button-back" t-on-click="close">KEMBALI</button>
                <button type="button" class="ut-logout-button ut-logout-button-confirm" t-on-click="confirmLogout">KELUAR</button>
            </div>
        </section>
    </div>
`;

function isModifiedClick(event) {
    return event.defaultPrevented
        || event.button !== 0
        || event.metaKey
        || event.ctrlKey
        || event.shiftKey
        || event.altKey;
}

function isLogoutUrl(value) {
    if (!value) {
        return false;
    }
    try {
        const url = new URL(value, window.location.origin);
        return url.pathname === LOGOUT_PATH;
    } catch (error) {
        return String(value).includes(LOGOUT_PATH);
    }
}

export class UnitradeLogoutConfirm extends Component {
    static template = LOGOUT_CONFIRM_TEMPLATE;

    setup() {
        this.cancelButtonRef = useRef("cancelButton");
        this.state = useState({
            rendered: false,
            open: false,
        });
        this.pendingLogout = null;
        this.closeTimer = null;
        this.previousBodyOverflow = "";
        this.lastTrigger = null;
        this.onDocumentClick = (event) => this.interceptLogoutLink(event);
        this.onDocumentSubmit = (event) => this.interceptLogoutForm(event);
        this.onKeydown = (event) => {
            if (event.key === "Escape" && this.state.rendered) {
                this.close();
            }
        };

        onMounted(() => {
            document.addEventListener("click", this.onDocumentClick, true);
            document.addEventListener("submit", this.onDocumentSubmit, true);
            document.addEventListener("keydown", this.onKeydown);
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this.onDocumentClick, true);
            document.removeEventListener("submit", this.onDocumentSubmit, true);
            document.removeEventListener("keydown", this.onKeydown);
            window.clearTimeout(this.closeTimer);
            this.restoreBodyOverflow();
        });
    }

    get modalClass() {
        return this.state.open ? "ut-logout-modal is-open" : "ut-logout-modal";
    }

    interceptLogoutLink(event) {
        const target = event.target;
        const link = target && target.closest ? target.closest("a[href]") : null;
        if (!link || !document.documentElement.contains(link)) {
            return;
        }
        if (!isLogoutUrl(link.getAttribute("href")) || isModifiedClick(event)) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        this.open({
            type: "link",
            href: link.href,
        }, link);
    }

    interceptLogoutForm(event) {
        const form = event.target;
        if (!form || form.dataset.utLogoutConfirmed === "1") {
            return;
        }
        const submitter = event.submitter || null;
        const action = submitter?.getAttribute("formaction") || form.getAttribute("action") || window.location.href;
        if (!isLogoutUrl(action)) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        this.open({
            type: "form",
            form,
            submitter,
        }, submitter || form);
    }

    open(pendingLogout, trigger) {
        window.clearTimeout(this.closeTimer);
        this.pendingLogout = pendingLogout;
        this.lastTrigger = trigger || null;
        this.previousBodyOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        this.state.rendered = true;

        window.requestAnimationFrame(() => {
            this.state.open = true;
            window.setTimeout(() => {
                if (this.cancelButtonRef.el) {
                    this.cancelButtonRef.el.focus({ preventScroll: true });
                }
            }, 0);
        });
    }

    restoreBodyOverflow() {
        document.body.style.overflow = this.previousBodyOverflow || "";
    }

    close() {
        if (!this.state.rendered) {
            return;
        }
        this.state.open = false;
        this.restoreBodyOverflow();
        this.pendingLogout = null;
        const focusTarget = this.lastTrigger;
        this.closeTimer = window.setTimeout(() => {
            this.state.rendered = false;
            this.lastTrigger = null;
            if (focusTarget && focusTarget.focus) {
                focusTarget.focus({ preventScroll: true });
            }
        }, CLOSE_ANIMATION_MS);
    }

    confirmLogout() {
        const pendingLogout = this.pendingLogout;
        this.state.open = false;
        this.restoreBodyOverflow();

        if (!pendingLogout) {
            this.close();
            return;
        }

        if (pendingLogout.type === "form" && pendingLogout.form) {
            pendingLogout.form.dataset.utLogoutConfirmed = "1";
            window.requestAnimationFrame(() => {
                if (pendingLogout.form.requestSubmit) {
                    pendingLogout.form.requestSubmit(pendingLogout.submitter || undefined);
                } else {
                    pendingLogout.form.submit();
                }
            });
            return;
        }

        if (pendingLogout.href) {
            window.location.assign(pendingLogout.href);
        }
    }
}

async function mountLogoutConfirm() {
    if (document.documentElement.dataset.utLogoutConfirmMounted === "1") {
        return;
    }
    document.documentElement.dataset.utLogoutConfirmMounted = "1";
    let target = document.getElementById("unitrade-logout-confirm-root");
    if (!target) {
        target = document.createElement("div");
        target.id = "unitrade-logout-confirm-root";
        document.body.appendChild(target);
    }
    await mount(UnitradeLogoutConfirm, target);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountLogoutConfirm(), { once: true });
} else {
    mountLogoutConfirm();
}
