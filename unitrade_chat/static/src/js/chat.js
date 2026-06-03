/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

const POLL_INTERVAL = 8000;
const POLL_INTERVAL_FAST = 4000;
const POLL_INTERVAL_SLOW = 15000;
const PRESENCE_INTERVAL = 30000;
const REPORT_IMAGE_MAX_FILES = 3;
const REPORT_IMAGE_MAX_BYTES = 2 * 1024 * 1024;
const REPORT_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

function intOrDefault(value, fallback = 0) {
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function upsertById(items, incoming) {
    const index = items.findIndex((item) => item.id === incoming.id || (incoming.chat_key && item.chat_key === incoming.chat_key));
    if (index === -1) {
        items.unshift(incoming);
    } else {
        items.splice(index, 1, incoming);
    }
    if (incoming.chat_key) {
        for (let i = items.length - 1; i >= 0; i--) {
            if (i !== items.findIndex((item) => item.chat_key === incoming.chat_key) && items[i].chat_key === incoming.chat_key) {
                items.splice(i, 1);
            }
        }
    }
}

export class UnitradeChatApp extends Component {
    static template = "unitrade_chat.ChatApp";
    static props = {
        initialConversationId: { type: Number, optional: true },
        role: { type: String, optional: true },
        basePath: { type: String, optional: true },
        busService: { type: Object, optional: true },
    };
    static defaultProps = {
        initialConversationId: 0,
        role: "buyer",
        basePath: "/unitrade/chat",
        busService: null,
    };

    setup() {
        this.rootRef = useRef("root");
        this.messageListRef = useRef("messageList");
        this.imageInputRef = useRef("imageInput");
        this.reportProofInputRef = useRef("reportProofInput");
        this.messageInputRef = useRef("messageInput");
        this.busService = this.props.busService;
        this.pollTimer = null;
        this.presenceTimer = null;
        this.typingTimer = null;
        this.typingIdleTimer = null;
        this.otherTypingTimer = null;
        this.pollDelay = POLL_INTERVAL;
        this.busHandlersBound = false;
        this.subscribedChannels = new Set();
        this.pendingSeq = 0;
        this.lastReadSentByConversation = new Map();
        this.readReceiptTimer = null;
        this.onDocumentClick = (ev) => {
            const target = ev.target;
            if (this.state.attachMenuOpen && target && target.closest && !target.closest(".ut-chat-attach-wrap")) {
                this.state.attachMenuOpen = false;
            }
            if (this.state.headerMenuOpen && target && target.closest && !target.closest(".ut-chat-header-menu-wrap")) {
                this.state.headerMenuOpen = false;
            }
        };
        this.onWindowFocus = () => this.scheduleVisibleReadReceipt();
        this.onVisibilityChange = () => this.scheduleVisibleReadReceipt();
        this.state = useState({
            loading: true,
            messagesLoading: false,
            sending: false,
            error: "",
            currentUserId: 0,
            currentUserAvatarUrl: "/web/static/img/user_menu_avatar.png",
            isSellerView: false,
            conversations: [],
            activeConversationId: this.props.initialConversationId || 0,
            messages: [],
            hasMoreMessages: false,
            loadingOlder: false,
            products: [],
            composer: "",
            uploadStatus: "",
            otherTyping: false,
            attachMenuOpen: false,
            headerMenuOpen: false,
            productPickerOpen: false,
            reportModalOpen: false,
            reportReason: "",
            reportProofs: [],
            reportDragActive: false,
            reportSubmitting: false,
            reportError: "",
            reportSuccess: "",
            mobileConversationOpen: Boolean(this.props.initialConversationId),
        });

        onMounted(() => {
            document.addEventListener("click", this.onDocumentClick);
            document.addEventListener("visibilitychange", this.onVisibilityChange);
            window.addEventListener("focus", this.onWindowFocus);
            this.bootstrap();
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this.onDocumentClick);
            document.removeEventListener("visibilitychange", this.onVisibilityChange);
            window.removeEventListener("focus", this.onWindowFocus);
            this.stopTimers();
            this.unsubscribeChannels();
        });

        useEffect(
            () => {
                if (!this.state.loadingOlder && !this.state.messagesLoading) {
                    this.scrollToBottom({ retries: 4 });
                }
            },
            () => [this.state.messages.length, this.state.activeConversationId, this.state.messagesLoading]
        );
    }

    get activeConversation() {
        return this.state.conversations.find((conversation) => conversation.id === this.state.activeConversationId) || null;
    }

    get todayLabel() {
        return new Date().toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" });
    }

    get sidebarTitle() {
        return this.chatRole === "seller" ? "Chat Pembeli" : "Chat Penjual";
    }

    get chatRole() {
        return this.props.role === "seller" ? "seller" : "buyer";
    }

    get basePath() {
        return this.props.basePath || (this.chatRole === "seller" ? "/unitrade/seller/chat" : "/unitrade/chat");
    }

    rpcPayload(payload = {}) {
        return {
            role: this.chatRole,
            ...payload,
        };
    }

    get reportFormValid() {
        return Boolean((this.state.reportReason || "").trim() && !this.state.reportSubmitting);
    }

    conversationItemClass(conversation) {
        const base = "ut-chat-list-item";
        return conversation.id === this.state.activeConversationId ? `${base} ut-is-active` : base;
    }

    messageClass(message) {
        const typeClass = `ut-is-${message.type || "text"}-message`;
        const sideClass = message.is_mine ? "ut-is-mine" : "ut-is-theirs";
        const systemClass = message.type === "system" ? " ut-is-system" : "";
        return `ut-chat-message ${sideClass}${systemClass} ${typeClass}`;
    }

    normalizeConversation(conversation) {
        if (!conversation) {
            return conversation;
        }
        return {
            ...conversation,
            id: Number(conversation.id),
            buyer_user_id: Number(conversation.buyer_user_id || 0),
            seller_user_id: Number(conversation.seller_user_id || 0),
            counterpart_user_id: Number(conversation.counterpart_user_id || 0),
            avatar_url: conversation.avatar_url || "/web/static/img/user_menu_avatar.png",
        };
    }

    normalizeMessage(message) {
        if (!message) {
            return message;
        }
        const authorUserId = Number(message.author_user_id || 0);
        const conversation = this.state.conversations.find((item) => item.id === Number(message.conversation_id || 0)) || this.activeConversation;
        let avatarUrl = message.author_avatar_url || "";
        if (!avatarUrl && conversation) {
            if (authorUserId === conversation.buyer_user_id) {
                avatarUrl = conversation.buyer_avatar_url;
            } else if (authorUserId === conversation.seller_user_id) {
                avatarUrl = conversation.seller_avatar_url;
            }
        }
        return {
            ...message,
            author_user_id: authorUserId,
            conversation_id: Number(message.conversation_id || 0),
            author_avatar_url: avatarUrl || "/web/static/img/user_menu_avatar.png",
            is_mine: Boolean(this.state.currentUserId && authorUserId === this.state.currentUserId),
        };
    }

    normalizeMessages(messages) {
        return (messages || []).map((message) => this.normalizeMessage(message));
    }

    async bootstrap() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/chat/bootstrap", this.rpcPayload({
                conversation_id: this.state.activeConversationId || false,
            }));
            if (!result.success) {
                throw new Error(result.message || "Chat gagal dimuat.");
            }
            this.state.currentUserId = Number(result.user_id || 0);
            this.state.currentUserAvatarUrl = result.current_user_avatar_url || "/web/static/img/user_menu_avatar.png";
            this.state.isSellerView = Boolean(result.is_seller_view);
            this.state.conversations = (result.conversations || []).map((conversation) => this.normalizeConversation(conversation));
            this.state.activeConversationId = result.active_conversation_id || 0;
            this.state.mobileConversationOpen = Boolean(this.state.activeConversationId);
            this.state.messages = this.normalizeMessages(result.messages);
            this.state.hasMoreMessages = Boolean(result.has_more_messages);
            this.state.products = result.products || [];
            this.subscribe(result.user_channel);
            const active = this.activeConversation;
            if (active) {
                this.subscribe(active.conversation_channel || active.bus_channel);
            }
            this.startTimers();
            this.scheduleVisibleReadReceipt();
        } catch (error) {
            console.error("[UniTrade] Chat bootstrap:", error);
            this.state.error = "Chat belum bisa dimuat.";
        } finally {
            this.state.loading = false;
            this.scrollToBottom({ retries: 6 });
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
            this.busService.subscribe("unitrade_chat_message", (payload) => this.onBusMessage(payload));
            this.busService.subscribe("unitrade_chat_notification", (payload) => this.onBusNotification(payload));
            this.busService.subscribe("unitrade_chat_read", (payload) => this.onBusRead(payload));
            this.busService.subscribe("unitrade_chat_presence", (payload) => this.onBusPresence(payload));
            this.busService.subscribe("unitrade_chat_typing", (payload) => this.onBusTyping(payload));
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
        if (payload && payload.messages_by_user && this.state.currentUserId) {
            payload = payload.messages_by_user[this.state.currentUserId] || payload.messages_by_user[String(this.state.currentUserId)];
        }
        this.onBusNotification(payload);
    }

    onBusNotification(payload) {
        if (!payload || !payload.conversation || !payload.message) {
            return;
        }
        const conversation = this.normalizeConversation(payload.conversation);
        const message = this.normalizeMessage(payload.message);
        upsertById(this.state.conversations, conversation);
        if (conversation.id === this.state.activeConversationId) {
            if (!this.consumeMatchingPending(message) && !this.state.messages.some((existing) => existing.id === message.id)) {
                this.state.messages.push(message);
            }
            this.scheduleVisibleReadReceipt();
        }
    }

    onBusRead(payload) {
        if (!payload || payload.conversation_id !== this.state.activeConversationId) {
            return;
        }
        this.state.messages.forEach((message) => {
            if (message.is_mine && (!payload.last_seen_message_id || Number(message.id) <= Number(payload.last_seen_message_id))) {
                message.read = true;
                message.delivery_state = "read";
            }
        });
    }

    onBusPresence(payload) {
        if (!payload || !payload.user_id) {
            return;
        }
        this.state.conversations.forEach((conversation) => {
            if (conversation.counterpart_user_id === payload.user_id) {
                conversation.online = true;
                conversation.last_seen_label = "Online";
            }
        });
    }

    onBusTyping(payload) {
        if (!payload || payload.conversation_id !== this.state.activeConversationId || payload.user_id === this.state.currentUserId) {
            return;
        }
        this.state.otherTyping = Boolean(payload.typing);
        if (this.otherTypingTimer) {
            window.clearTimeout(this.otherTypingTimer);
        }
        if (payload.typing) {
            this.otherTypingTimer = window.setTimeout(() => {
                this.state.otherTyping = false;
            }, 3500);
        }
    }

    startTimers() {
        this.stopTimers();
        this.schedulePoll(POLL_INTERVAL_FAST);
        this.presenceTimer = window.setInterval(() => this.sendPresence(), PRESENCE_INTERVAL);
        this.sendPresence();
    }

    stopTimers() {
        if (this.pollTimer) {
            window.clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        if (this.presenceTimer) {
            window.clearInterval(this.presenceTimer);
            this.presenceTimer = null;
        }
        if (this.typingTimer) {
            window.clearTimeout(this.typingTimer);
            this.typingTimer = null;
        }
        if (this.typingIdleTimer) {
            window.clearTimeout(this.typingIdleTimer);
            this.typingIdleTimer = null;
        }
        if (this.otherTypingTimer) {
            window.clearTimeout(this.otherTypingTimer);
            this.otherTypingTimer = null;
        }
        if (this.readReceiptTimer) {
            window.clearTimeout(this.readReceiptTimer);
            this.readReceiptTimer = null;
        }
    }

    schedulePoll(delay = this.pollDelay) {
        if (this.pollTimer) {
            window.clearTimeout(this.pollTimer);
        }
        this.pollDelay = delay;
        this.pollTimer = window.setTimeout(async () => {
            await this.pollMessages();
            this.schedulePoll(this.pollDelay);
        }, delay);
    }

    async selectConversation(conversationId) {
        if (conversationId === this.state.activeConversationId && this.state.mobileConversationOpen) {
            this.scrollToBottom({ retries: 4 });
            return;
        }
        this.state.activeConversationId = conversationId;
        this.state.mobileConversationOpen = true;
        this.state.messagesLoading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/chat/conversation", this.rpcPayload({ conversation_id: conversationId }));
            if (!result.success) {
                throw new Error(result.message || "Percakapan gagal dimuat.");
            }
            const conversation = this.normalizeConversation(result.conversation);
            upsertById(this.state.conversations, conversation);
            this.state.activeConversationId = conversation.id;
            this.state.isSellerView = Boolean(conversation.is_seller_view);
            this.state.messages = this.normalizeMessages(result.messages);
            this.state.hasMoreMessages = Boolean(result.has_more);
            this.state.products = result.products || [];
            this.subscribe(conversation.conversation_channel || conversation.bus_channel);
            window.history.replaceState({}, "", `${this.basePath}?conversation_id=${conversation.id}`);
            this.scheduleVisibleReadReceipt();
        } catch (error) {
            console.error("[UniTrade] Chat conversation:", error);
            this.state.error = "Percakapan gagal dimuat.";
        } finally {
            this.state.messagesLoading = false;
            this.scrollToBottom({ retries: 6 });
        }
    }

    backToList() {
        this.state.mobileConversationOpen = false;
    }

    async pollMessages() {
        if (!this.state.activeConversationId) {
            return;
        }
        const lastMessage = [...this.state.messages].reverse().find((message) => !message.pending && Number.isFinite(Number(message.id)));
        try {
            const result = await jsonrpc("/unitrade/chat/messages", this.rpcPayload({
                conversation_id: this.state.activeConversationId,
                after_id: lastMessage ? lastMessage.id : 0,
            }));
            if (!result.success) {
                return;
            }
            if (result.conversation) {
                upsertById(this.state.conversations, this.normalizeConversation(result.conversation));
            }
            let newCount = 0;
            (result.messages || []).forEach((message) => {
                const normalized = this.normalizeMessage(message);
                if (!this.consumeMatchingPending(normalized) && !this.state.messages.some((existing) => existing.id === normalized.id)) {
                    this.state.messages.push(normalized);
                    newCount++;
                }
            });
            if (newCount) {
                this.scrollToBottom({ retries: 3 });
                this.scheduleVisibleReadReceipt();
            }
            this.pollDelay = newCount ? POLL_INTERVAL_FAST : POLL_INTERVAL_SLOW;
        } catch (error) {
            console.warn("[UniTrade] Chat polling failed:", error);
            this.pollDelay = Math.min((this.pollDelay || POLL_INTERVAL) * 2, 30000);
        }
    }

    async loadOlderMessages() {
        if (!this.state.activeConversationId || !this.state.hasMoreMessages || this.state.loadingOlder) {
            return;
        }
        const firstMessage = this.state.messages.find((message) => !message.pending && Number.isFinite(Number(message.id)));
        if (!firstMessage) {
            return;
        }
        const el = this.messageListRef.el;
        const previousHeight = el ? el.scrollHeight : 0;
        this.state.loadingOlder = true;
        try {
            const result = await jsonrpc("/unitrade/chat/messages", this.rpcPayload({
                conversation_id: this.state.activeConversationId,
                before_id: firstMessage.id,
                limit: 40,
            }));
            if (!result.success) {
                return;
            }
            const older = this.normalizeMessages(result.messages).filter(
                (message) => !this.state.messages.some((existing) => existing.id === message.id)
            );
            this.state.messages.unshift(...older);
            this.state.hasMoreMessages = Boolean(result.has_more);
            window.setTimeout(() => {
                if (el) {
                    el.scrollTop = el.scrollHeight - previousHeight;
                }
            }, 0);
        } catch (error) {
            console.warn("[UniTrade] Chat older messages failed:", error);
        } finally {
            this.state.loadingOlder = false;
        }
    }

    onMessagesScroll() {
        const el = this.messageListRef.el;
        if (el && el.scrollTop < 80) {
            this.loadOlderMessages();
        }
        this.scheduleVisibleReadReceipt();
    }

    async sendPresence() {
        if (!this.state.activeConversationId) {
            return;
        }
        try {
            const result = await jsonrpc("/unitrade/chat/presence", this.rpcPayload({
                conversation_id: this.state.activeConversationId,
            }));
            if (result.success && result.conversation) {
                upsertById(this.state.conversations, this.normalizeConversation(result.conversation));
            }
        } catch (error) {
            console.warn("[UniTrade] Chat presence failed:", error);
        }
    }

    isPageReadyForReadReceipt() {
        return document.visibilityState === "visible" && document.hasFocus() && Boolean(this.state.activeConversationId);
    }

    getLastVisibleIncomingMessageId() {
        if (!this.isPageReadyForReadReceipt()) {
            return 0;
        }
        const el = this.messageListRef.el;
        if (!el) {
            return 0;
        }
        const containerRect = el.getBoundingClientRect();
        const visibleTop = containerRect.top;
        const visibleBottom = containerRect.bottom;
        let lastVisibleId = 0;
        el.querySelectorAll(".ut-chat-message[data-message-id]").forEach((node) => {
            const id = Number(node.dataset.messageId || 0);
            const authorUserId = Number(node.dataset.authorUserId || 0);
            if (!id || authorUserId === this.state.currentUserId) {
                return;
            }
            const rect = node.getBoundingClientRect();
            const visibleHeight = Math.max(0, Math.min(rect.bottom, visibleBottom) - Math.max(rect.top, visibleTop));
            const visibilityRatio = rect.height ? visibleHeight / rect.height : 0;
            const isVisible = visibilityRatio >= 0.6 || visibleHeight >= 48;
            if (isVisible) {
                lastVisibleId = Math.max(lastVisibleId, id);
            }
        });
        return lastVisibleId;
    }

    scheduleVisibleReadReceipt() {
        if (this.readReceiptTimer) {
            window.clearTimeout(this.readReceiptTimer);
        }
        this.readReceiptTimer = window.setTimeout(() => this.markVisibleMessagesRead(), 180);
    }

    async markVisibleMessagesRead() {
        if (!this.isPageReadyForReadReceipt()) {
            return;
        }
        const lastSeenMessageId = this.getLastVisibleIncomingMessageId();
        if (!lastSeenMessageId) {
            return;
        }
        const previous = Number(this.lastReadSentByConversation.get(this.state.activeConversationId) || 0);
        if (lastSeenMessageId <= previous) {
            return;
        }
        try {
            const result = await jsonrpc("/unitrade/chat/read", this.rpcPayload({
                conversation_id: this.state.activeConversationId,
                active_conversation_id: this.state.activeConversationId,
                receiver_id: this.state.currentUserId,
                last_seen_message_id: lastSeenMessageId,
                page_visible: document.visibilityState === "visible",
                window_focused: document.hasFocus(),
            }));
            if (result.success && result.conversation) {
                this.lastReadSentByConversation.set(this.state.activeConversationId, lastSeenMessageId);
                upsertById(this.state.conversations, this.normalizeConversation(result.conversation));
            }
        } catch (error) {
            console.warn("[UniTrade] Chat read failed:", error);
        }
    }

    applyQuickReply(text) {
        this.state.composer = text;
        this.messageInputRef.el?.focus();
        this.sendTyping(true);
    }

    onComposerInput() {
        this.sendTyping(true);
        if (this.typingIdleTimer) {
            window.clearTimeout(this.typingIdleTimer);
        }
        this.typingIdleTimer = window.setTimeout(() => this.sendTyping(false), 1300);
    }

    sendTyping(isTyping) {
        if (!this.state.activeConversationId) {
            return;
        }
        if (this.typingTimer) {
            window.clearTimeout(this.typingTimer);
        }
        this.typingTimer = window.setTimeout(async () => {
            try {
                await jsonrpc("/unitrade/chat/typing", this.rpcPayload({
                    conversation_id: this.state.activeConversationId,
                    typing: isTyping,
                }));
            } catch (error) {
                console.warn("[UniTrade] Chat typing failed:", error);
            }
        }, isTyping ? 220 : 0);
    }

    async sendText() {
        const body = this.state.composer.trim();
        if (!body || this.state.sending || !this.state.activeConversationId) {
            return;
        }
        await this.sendPayload({ message_type: "text", body }, { optimistic: true });
        this.state.composer = "";
    }

    toggleAttachMenu(ev) {
        if (ev && ev.stopPropagation) {
            ev.stopPropagation();
        }
        this.state.attachMenuOpen = !this.state.attachMenuOpen;
        if (this.state.attachMenuOpen) {
            this.state.productPickerOpen = false;
        }
    }

    toggleHeaderMenu(ev) {
        if (ev && ev.stopPropagation) {
            ev.stopPropagation();
        }
        this.state.headerMenuOpen = !this.state.headerMenuOpen;
        this.state.attachMenuOpen = false;
    }

    configureChatReceiving() {
        this.state.headerMenuOpen = false;
        window.location.href = "/unitrade/seller/settings";
    }

    openReportModal() {
        this.state.headerMenuOpen = false;
        this.state.reportModalOpen = true;
        this.state.reportReason = "";
        this.state.reportProofs = [];
        this.state.reportDragActive = false;
        this.state.reportError = "";
        this.state.reportSuccess = "";
    }

    closeReportModal() {
        if (this.state.reportSubmitting) {
            return;
        }
        this.state.reportModalOpen = false;
    }

    setReportReason(reason) {
        this.state.reportReason = reason;
        this.state.reportError = "";
    }

    chooseReportProof() {
        this.reportProofInputRef.el?.click();
    }

    onReportProofChange(ev) {
        const files = Array.from(ev.target.files || []);
        ev.target.value = "";
        this.handleReportProofFiles(files);
    }

    onReportProofDragEnter(ev) {
        ev.preventDefault();
        this.state.reportDragActive = true;
    }

    onReportProofDragOver(ev) {
        ev.preventDefault();
        this.state.reportDragActive = true;
    }

    onReportProofDragLeave(ev) {
        ev.preventDefault();
        if (ev.currentTarget === ev.target) {
            this.state.reportDragActive = false;
        }
    }

    onReportProofDrop(ev) {
        ev.preventDefault();
        this.state.reportDragActive = false;
        this.handleReportProofFiles(Array.from(ev.dataTransfer?.files || []));
    }

    handleReportProofFiles(files) {
        if (!files.length) {
            return;
        }
        this.state.reportError = "";
        const availableSlots = REPORT_IMAGE_MAX_FILES - this.state.reportProofs.length;
        if (availableSlots <= 0 || files.length > availableSlots) {
            this.state.reportError = "Maksimal upload 3 gambar bukti laporan.";
            return;
        }
        files.slice(0, availableSlots).forEach((file) => {
            if (!REPORT_IMAGE_TYPES.includes(file.type)) {
                this.state.reportError = "Format bukti harus JPG, PNG, atau WebP.";
                return;
            }
            if (file.size > REPORT_IMAGE_MAX_BYTES) {
                this.state.reportError = "Ukuran setiap bukti foto maksimal 2 MB.";
                return;
            }
            const reader = new FileReader();
            reader.onload = () => {
                this.state.reportProofs.push({
                    id: `proof-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                    data: reader.result,
                    preview: reader.result,
                    filename: file.name,
                    mimetype: file.type,
                    size: file.size,
                });
            };
            reader.onerror = () => {
                this.state.reportError = "Bukti foto gagal dibaca.";
            };
            reader.readAsDataURL(file);
        });
    }

    removeReportProof(proofId) {
        const index = this.state.reportProofs.findIndex((proof) => proof.id === proofId);
        if (index !== -1) {
            this.state.reportProofs.splice(index, 1);
            this.state.reportError = "";
        }
    }

    async submitReport() {
        if (!this.reportFormValid || !this.state.activeConversationId) {
            return;
        }
        this.state.reportSubmitting = true;
        this.state.reportError = "";
        this.state.reportSuccess = "";
        try {
            const result = await jsonrpc("/unitrade/chat/report", this.rpcPayload({
                conversation_id: this.state.activeConversationId,
                reason: this.state.reportReason.trim(),
                proof_images: this.state.reportProofs.map((proof) => ({
                    data: proof.data,
                    filename: proof.filename,
                    mimetype: proof.mimetype,
                })),
            }));
            if (!result.success) {
                throw new Error(result.message || "Laporan gagal dikirim.");
            }
            this.state.reportSuccess = result.message || "Laporan berhasil dikirim.";
            window.setTimeout(() => {
                this.state.reportModalOpen = false;
            }, 700);
        } catch (error) {
            console.error("[UniTrade] Chat report:", error);
            this.state.reportError = error.message || "Laporan gagal dikirim.";
        } finally {
            this.state.reportSubmitting = false;
        }
    }

    chooseImage() {
        this.state.attachMenuOpen = false;
        this.state.productPickerOpen = false;
        this.openImagePicker();
    }

    chooseProduct() {
        this.state.attachMenuOpen = false;
        this.state.productPickerOpen = true;
    }

    toggleProductPicker() {
        this.state.attachMenuOpen = false;
        this.state.productPickerOpen = !this.state.productPickerOpen;
    }

    async sendProduct(productId) {
        const product = this.state.products.find((item) => item.id === productId) || null;
        this.state.productPickerOpen = false;
        await this.sendPayload(
            {
                message_type: "product",
                product_id: productId,
                body: product ? product.name : "",
            },
            {
                optimistic: true,
                preview: { product },
            }
        );
    }

    async addProductToCart(productId, checkout = false, ev = null) {
        if (ev && ev.preventDefault) {
            ev.preventDefault();
        }
        if (ev && ev.stopPropagation) {
            ev.stopPropagation();
        }
        if (!productId || !this.state.activeConversationId) {
            return;
        }
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/chat/cart/add", this.rpcPayload({
                conversation_id: this.state.activeConversationId,
                product_id: productId,
                checkout,
            }));
            if (!result.success) {
                throw new Error(result.message || "Produk gagal ditambahkan ke keranjang.");
            }
            if (checkout && result.checkout_url) {
                window.location.href = result.checkout_url;
            }
        } catch (error) {
            console.error("[UniTrade] Chat cart:", error);
            this.state.error = error.message || "Produk gagal ditambahkan ke keranjang.";
        }
    }

    openImagePicker() {
        this.state.attachMenuOpen = false;
        this.imageInputRef.el?.click();
    }

    onImageChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
            this.state.error = "Format gambar harus JPG, PNG, atau WebP.";
            return;
        }
        if (file.size > 2 * 1024 * 1024) {
            this.state.error = "Ukuran gambar maksimal 2 MB.";
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            this.state.uploadStatus = "Mengunggah gambar...";
            this.sendPayload(
                {
                    message_type: "image",
                    image_data: reader.result,
                    filename: file.name,
                    mimetype: file.type,
                },
                {
                    optimistic: true,
                    preview: {
                        image_url: reader.result,
                        body: file.name,
                    },
                }
            );
        };
        reader.onerror = () => {
            this.state.error = "Gambar gagal dibaca.";
        };
        reader.readAsDataURL(file);
    }

    async sendPayload(payload, options = {}) {
        if (this.state.sending || !this.state.activeConversationId) {
            return;
        }
        const pendingId = options.optimistic ? this.addPendingMessage(payload, options.preview || {}) : null;
        this.state.sending = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/chat/send", this.rpcPayload({
                conversation_id: this.state.activeConversationId,
                ...payload,
            }));
            if (!result.success) {
                throw new Error(result.message || "Pesan gagal dikirim.");
            }
            if (pendingId) {
                this.replacePendingMessage(pendingId, this.normalizeMessage(result.message));
            } else {
                const message = this.normalizeMessage(result.message);
                if (!this.state.messages.some((existing) => existing.id === message.id)) {
                    this.state.messages.push(message);
                }
            }
            upsertById(this.state.conversations, this.normalizeConversation(result.conversation));
        } catch (error) {
            console.error("[UniTrade] Chat send:", error);
            this.state.error = error.message || "Pesan gagal dikirim.";
            if (pendingId) {
                this.markPendingFailed(pendingId, payload, options.preview || {});
            }
        } finally {
            this.state.sending = false;
            this.state.uploadStatus = "";
        }
    }

    addPendingMessage(payload, preview = {}) {
        const id = `pending-${Date.now()}-${++this.pendingSeq}`;
        const time = new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
        this.state.messages.push({
            id,
            conversation_id: this.state.activeConversationId,
            author_user_id: this.state.currentUserId,
            author_name: "",
            author_avatar_url: this.state.currentUserAvatarUrl,
            is_mine: true,
            type: payload.message_type || "text",
            body: preview.body || payload.body || "",
            time,
            date: "",
            read: false,
            delivered: false,
            delivery_state: "sending",
            pending: true,
            failed: false,
            retry_payload: payload,
            retry_preview: preview,
            image_url: preview.image_url || "",
            product: preview.product || null,
        });
        return id;
    }

    replacePendingMessage(pendingId, serverMessage) {
        const index = this.state.messages.findIndex((message) => message.id === pendingId);
        if (index !== -1) {
            this.state.messages.splice(index, 1, serverMessage);
        } else if (!this.state.messages.some((message) => message.id === serverMessage.id)) {
            this.state.messages.push(serverMessage);
        }
    }

    markPendingFailed(pendingId, payload, preview = {}) {
        const index = this.state.messages.findIndex((message) => message.id === pendingId);
        if (index !== -1) {
            this.state.messages[index].pending = false;
            this.state.messages[index].failed = true;
            this.state.messages[index].delivery_state = "failed";
            this.state.messages[index].retry_payload = payload;
            this.state.messages[index].retry_preview = preview;
        }
    }

    removePendingMessage(pendingId) {
        const index = this.state.messages.findIndex((message) => message.id === pendingId);
        if (index !== -1) {
            this.state.messages.splice(index, 1);
        }
    }

    retryMessage(message) {
        if (!message || !message.failed || !message.retry_payload) {
            return;
        }
        this.removePendingMessage(message.id);
        this.sendPayload(message.retry_payload, {
            optimistic: true,
            preview: message.retry_preview || {},
        });
    }

    consumeMatchingPending(serverMessage) {
        if (!serverMessage || !serverMessage.is_mine) {
            return false;
        }
        const index = this.state.messages.findIndex((message) => {
            if (!message.pending || message.type !== serverMessage.type) {
                return false;
            }
            if (serverMessage.type === "product") {
                return message.product && serverMessage.product && message.product.id === serverMessage.product.id;
            }
            if (serverMessage.type === "image") {
                return Boolean(message.image_url);
            }
            return message.body === serverMessage.body;
        });
        if (index === -1) {
            return false;
        }
        this.state.messages.splice(index, 1, serverMessage);
        return true;
    }

    deliveryLabel(message) {
        if (message.failed) {
            return "Gagal";
        }
        if (message.pending || message.delivery_state === "sending") {
            return message.type === "image" && this.state.uploadStatus ? this.state.uploadStatus : "Mengirim...";
        }
        if (message.read || message.delivery_state === "read") {
            return "Dibaca";
        }
        if (message.delivered || message.delivery_state === "delivered") {
            return "Terkirim";
        }
        return "Terkirim";
    }

    scrollToBottom(options = {}) {
        const retries = Number.isFinite(Number(options.retries)) ? Number(options.retries) : 2;
        const delay = Number.isFinite(Number(options.delay)) ? Number(options.delay) : 0;
        const run = (remaining) => {
            const el = this.messageListRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
                this.bindMediaScrollSync(el);
                this.scheduleVisibleReadReceipt();
            }
            if (remaining > 0) {
                window.requestAnimationFrame(() => run(remaining - 1));
            }
        };
        window.setTimeout(() => run(retries), delay);
    }

    bindMediaScrollSync(el) {
        if (!el) {
            return;
        }
        el.querySelectorAll("img").forEach((image) => {
            if (image.complete || image.dataset.utChatScrollBound === "1") {
                return;
            }
            image.dataset.utChatScrollBound = "1";
            image.addEventListener("load", () => this.scrollToBottom({ retries: 2 }), { once: true });
            image.addEventListener("error", () => this.scrollToBottom({ retries: 1 }), { once: true });
        });
    }
}

publicWidget.registry.UnitradeChatApp = publicWidget.Widget.extend({
    selector: "#ut-chat-owl",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const services = (Component.env && Component.env.services) || {};
        const props = {
            initialConversationId: intOrDefault(this.el.dataset.initialConversationId),
            role: this.el.dataset.chatRole === "seller" ? "seller" : "buyer",
            basePath: this.el.dataset.basePath || "/unitrade/chat",
            busService: services.bus_service || null,
        };
        const fallbackNodes = Array.from(this.el.childNodes);
        const mountTarget = document.createElement("div");
        mountTarget.className = "ut-chat-owl-mount-host";
        this.el.appendChild(mountTarget);
        try {
            this.component = await mount(UnitradeChatApp, mountTarget, { props, templates });
            fallbackNodes.forEach((node) => node.remove());
        } catch (error) {
            mountTarget.remove();
            console.error("[UniTrade] Chat mount:", error);
            this.el.classList.add("ut-chat-mount-failed");
            if (!this.el.querySelector(".ut-chat-mount-error")) {
                const fallback = document.createElement("div");
                fallback.className = "ut-chat-mount-error";
                fallback.textContent = "Chat belum bisa dimuat. Muat ulang halaman setelah modul di-upgrade.";
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
