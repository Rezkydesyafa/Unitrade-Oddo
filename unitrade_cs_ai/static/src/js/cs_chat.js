/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

export class CsFloatingChat extends Component {
    static template = "unitrade_cs_ai.CsFloatingChat";
    static props = {
        busService: { type: Object, optional: true },
    };
    static defaultProps = {
        busService: null,
    };

    setup() {
        this.messagesRef = useRef("messages");
        this.inputRef = useRef("input");
        this.panelRef = useRef("panel");
        this.busService = this.props.busService;
        this.busHandlersBound = false;
        this.subscribedChannels = new Set();
        this.bootstrapped = false;
        this.state = useState({
            open: false,
            loading: false,
            sending: false,
            aiTyping: false,
            error: "",
            session: { id: 0, state: "ai_active", can_escalate: true },
            messages: [],
            quickReplies: [],
        });
        this.onExternalOpen = (ev) => this.openExternal(ev && ev.detail ? ev.detail : {});
        onMounted(() => window.addEventListener("unitrade_cs:open", this.onExternalOpen));
        onWillUnmount(() => {
            window.removeEventListener("unitrade_cs:open", this.onExternalOpen);
            this.unsubscribeChannels();
        });
    }

    async openExternal(detail) {
        if (!this.state.open) {
            this.state.open = true;
            if (!this.bootstrapped) {
                await this.bootstrap();
            } else {
                this.scrollToBottom();
            }
        }
        const topic = detail && detail.topic ? String(detail.topic) : "";
        if (topic) {
            window.requestAnimationFrame(() => {
                if (this.inputRef.el && this.state.session.state !== "closed") {
                    this.inputRef.el.value = topic;
                    this.inputRef.el.focus();
                }
            });
        }
    }

    get statusLabel() {
        const map = {
            ai_active: "Asisten AI aktif",
            waiting_admin: "Menunggu admin",
            admin_handling: "Terhubung dengan admin",
            closed: "Sesi selesai",
        };
        return map[this.state.session.state] || "Customer Service";
    }

    get showQuickReplies() {
        return (
            this.state.session.state === "ai_active"
            && this.state.quickReplies.length
            && this.state.messages.filter((m) => m.author_type === "user").length === 0
        );
    }

    messageClass(message) {
        return message.author_type === "user"
            ? "ut-csai-msg ut-csai-mine"
            : "ut-csai-msg ut-csai-theirs";
    }

    badgeClass(message) {
        return message.author_type === "ai" ? "ut-csai-badge ut-csai-badge-ai" : "ut-csai-badge ut-csai-badge-admin";
    }

    badgeLabel(message) {
        return message.author_type === "ai" ? "AI" : "Admin";
    }

    async toggle() {
        this.state.open = !this.state.open;
        if (this.state.open && !this.bootstrapped) {
            await this.bootstrap();
        } else if (this.state.open) {
            this.scrollToBottom();
        }
    }

    async bootstrap() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/customer-service/chat/session", {});
            if (!result || !result.success) {
                this.state.error = (result && result.message) || "Customer Service gagal dimuat.";
                return;
            }
            this.bootstrapped = true;
            this.state.session = result.session;
            this.state.messages = result.messages || [];
            this.state.quickReplies = result.quick_replies || [];
            this.subscribe(result.session.bus_channel);
        } catch (error) {
            console.error("[UniTrade] CS bootstrap:", error);
            this.state.error = "Customer Service gagal dimuat.";
        } finally {
            this.state.loading = false;
            this.scrollToBottom();
        }
    }

    subscribe(channel) {
        if (!channel || !this.busService || this.subscribedChannels.has(channel)) {
            return;
        }
        this.subscribedChannels.add(channel);
        this.busService.addChannel(channel);
        if (!this.busHandlersBound) {
            this.busHandlersBound = true;
            this.busService.subscribe("unitrade_cs_message", (payload) => this.onBusMessage(payload));
        }
        this.busService.start();
    }

    unsubscribeChannels() {
        if (!this.busService) {
            return;
        }
        this.subscribedChannels.forEach((channel) => this.busService.deleteChannel(channel));
        this.subscribedChannels.clear();
    }

    onBusMessage(payload) {
        if (!payload || payload.session_id !== this.state.session.id) {
            return;
        }
        const message = payload.message;
        if (message && !this.state.messages.some((m) => m.id === message.id)) {
            this.state.messages.push(message);
            this.scrollToBottom();
        }
        if (payload.state) {
            this.state.session.state = payload.state;
            this.state.session.can_escalate = payload.state === "ai_active";
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    async send() {
        const input = this.inputRef.el;
        const body = input ? input.value.trim() : "";
        if (input) {
            input.value = "";
        }
        await this.sendText(body);
    }

    async sendText(body) {
        body = (body || "").trim();
        if (!body || this.state.sending) {
            return;
        }
        this.state.sending = true;
        this.state.error = "";
        if (this.state.session.state === "ai_active") {
            this.state.aiTyping = true;
        }
        this.scrollToBottom();
        try {
            const result = await jsonrpc("/customer-service/chat/send", {
                session_id: this.state.session.id,
                body,
            });
            if (!result || !result.success) {
                this.state.error = (result && result.message) || "Pesan gagal dikirim.";
                return;
            }
            this.state.session = result.session;
            this.appendIfNew(result.user_message);
            if (result.ai_message) {
                this.appendIfNew(result.ai_message);
            }
        } catch (error) {
            console.error("[UniTrade] CS send:", error);
            this.state.error = "Pesan gagal dikirim.";
        } finally {
            this.state.sending = false;
            this.state.aiTyping = false;
            this.scrollToBottom();
        }
    }

    appendIfNew(message) {
        if (message && !this.state.messages.some((m) => m.id === message.id)) {
            this.state.messages.push(message);
        }
    }

    async escalate() {
        this.state.error = "";
        try {
            const result = await jsonrpc("/customer-service/chat/escalate", {
                session_id: this.state.session.id,
            });
            if (!result || !result.success) {
                this.state.error = (result && result.message) || "Eskalasi gagal.";
                return;
            }
            this.state.session = result.session;
            this.scrollToBottom();
        } catch (error) {
            console.error("[UniTrade] CS escalate:", error);
            this.state.error = "Eskalasi gagal.";
        }
    }

    scrollToBottom() {
        const el = this.messagesRef.el;
        if (el) {
            window.requestAnimationFrame(() => {
                el.scrollTop = el.scrollHeight;
            });
        }
    }

    onResizeStart(ev) {
        ev.preventDefault();
        const panel = this.panelRef.el;
        if (!panel) {
            return;
        }
        const startX = ev.clientX;
        const startY = ev.clientY;
        const rect = panel.getBoundingClientRect();
        const startW = rect.width;
        const startH = rect.height;
        const minW = 320;
        const minH = 380;

        const onMove = (e) => {
            const maxW = window.innerWidth - 32;
            const maxH = window.innerHeight - 100;
            const newW = Math.min(Math.max(startW + (startX - e.clientX), minW), maxW);
            const newH = Math.min(Math.max(startH + (startY - e.clientY), minH), maxH);
            panel.style.width = newW + "px";
            panel.style.height = newH + "px";
        };
        const onUp = () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            document.body.style.userSelect = "";
        };
        document.body.style.userSelect = "none";
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
    }
}

publicWidget.registry.UnitradeCsFloatingChat = publicWidget.Widget.extend({
    selector: "#ut-csai-floating",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const services = (Component.env && Component.env.services) || {};
        const props = { busService: services.bus_service || null };
        try {
            this.component = await mount(CsFloatingChat, this.el, { props, templates });
        } catch (error) {
            console.error("[UniTrade] CS floating mount:", error);
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
