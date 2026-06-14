/* UniTrade Admin Dashboard — frontend script.
 *
 * Scope: only runs when .ut-admin-root exists (yaitu di halaman
 * /unitrade/admin*). Vanilla JS, tidak menyentuh OWL atau bundle backend.
 */
(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    function callJsonRpc(url, params) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: params || {},
            }),
        }).then(function (r) { return r.json(); });
    }

    ready(function () {
        var root = document.querySelector(".ut-admin-root");
        if (!root) return;

        // ---- Modal helpers -----------------------------------------------
        function openModal(id) {
            var el = document.getElementById(id);
            if (el) el.classList.add("ut-admin-show");
        }
        function closeModal(id) {
            var el = document.getElementById(id);
            if (el) el.classList.remove("ut-admin-show");
        }
        function escapeHtml(s) {
            return String(s == null ? "" : s)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }

        function ensureToastStack() {
            var stack = document.getElementById("utAdminToastStack");
            if (!stack) {
                stack = document.createElement("div");
                stack.id = "utAdminToastStack";
                stack.className = "ut-admin-toast-stack";
                root.appendChild(stack);
            }
            return stack;
        }

        function showToast(message, tone) {
            if (!message) return;
            var toast = document.createElement("div");
            toast.className = "ut-admin-toast ut-admin-toast-" + (tone || "info");
            toast.textContent = message;
            ensureToastStack().appendChild(toast);
            window.setTimeout(function () {
                toast.classList.add("ut-admin-toast-hide");
                window.setTimeout(function () { toast.remove(); }, 220);
            }, 2600);
        }

        function askAdmin(options) {
            options = options || {};
            return new Promise(function (resolve) {
                var overlay = document.createElement("div");
                var isPrompt = options.type === "prompt";
                var inputHtml = "";
                if (isPrompt) {
                    var inputTag = options.multiline ? "textarea" : "input";
                    inputHtml = "<" + inputTag +
                        ' class="ut-admin-dialog-input" ' +
                        (options.multiline ? "rows=\"4\"" : "type=\"text\"") +
                        ' placeholder="' + escapeHtml(options.placeholder || "") + '">' +
                        (options.multiline ? "</textarea>" : "");
                }
                overlay.className = "ut-admin-dialog-overlay";
                overlay.innerHTML =
                    '<div class="ut-admin-dialog" role="dialog" aria-modal="true">' +
                        '<div class="ut-admin-dialog-title">' + escapeHtml(options.title || "Konfirmasi") + '</div>' +
                        '<div class="ut-admin-dialog-message">' + escapeHtml(options.message || "") + '</div>' +
                        inputHtml +
                        '<div class="ut-admin-dialog-actions">' +
                            '<button type="button" class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" data-dialog-cancel>' +
                                escapeHtml(options.cancelLabel || "Batal") +
                            '</button>' +
                            '<button type="button" class="ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm" data-dialog-confirm>' +
                                escapeHtml(options.confirmLabel || "Ya") +
                            '</button>' +
                        '</div>' +
                    '</div>';
                root.appendChild(overlay);

                var input = overlay.querySelector(".ut-admin-dialog-input");
                var cleanup = function (value) {
                    overlay.remove();
                    resolve(value);
                };
                overlay.querySelector("[data-dialog-cancel]").addEventListener("click", function () {
                    cleanup(isPrompt ? null : false);
                });
                overlay.querySelector("[data-dialog-confirm]").addEventListener("click", function () {
                    if (!isPrompt) {
                        cleanup(true);
                        return;
                    }
                    cleanup(input ? input.value : "");
                });
                overlay.addEventListener("click", function (ev) {
                    if (ev.target === overlay) cleanup(isPrompt ? null : false);
                });
                overlay.addEventListener("keydown", function (ev) {
                    if (ev.key === "Escape") cleanup(isPrompt ? null : false);
                    if (ev.key === "Enter" && !options.multiline) {
                        ev.preventDefault();
                        overlay.querySelector("[data-dialog-confirm]").click();
                    }
                });
                if (input) input.focus();
                else overlay.querySelector("[data-dialog-confirm]").focus();
            });
        }

        function confirmAdmin(message, options) {
            options = options || {};
            options.message = message;
            options.type = "confirm";
            return askAdmin(options);
        }

        function promptAdmin(message, options) {
            options = options || {};
            options.message = message;
            options.type = "prompt";
            options.confirmLabel = options.confirmLabel || "Simpan";
            return askAdmin(options);
        }

        function openUserDetail(userId) {
            var body = document.getElementById("utAdminUserModalBody");
            if (!body) return;
            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminUserModal");
            callJsonRpc("/unitrade/admin/api/users/detail", { user_id: userId })
                .then(function (res) {
                    var d = res.result || {};
                    var seller = d.seller || { status: "none" };
                    var stats = d.stats || {};
                    var sellerStatusLabel = {
                        none: "Non-Penjual",
                        draft: "Draft",
                        pending: "Pending KTM",
                        verified: "Verified",
                        rejected: "Rejected",
                        revoked: "Revoked",
                    }[seller.status] || seller.status;

                    var statusBadge = d.is_blocked
                        ? '<span class="ut-admin-badge ut-admin-badge-red"><span class="ut-admin-badge-dot"></span>Diblokir</span>'
                        : '<span class="ut-admin-badge ut-admin-badge-green"><span class="ut-admin-badge-dot"></span>Aktif</span>';

                    var html = '';
                    html += '<div style="display:flex;align-items:center;gap:14px;margin-bottom:18px">';
                    html += '<div class="ut-admin-avatar" style="width:52px;height:52px;font-size:18px">' +
                            escapeHtml((d.name || "?")[0].toUpperCase()) + '</div>';
                    html += '<div style="flex:1"><div style="font-size:17px;font-weight:700">' + escapeHtml(d.name) + '</div>';
                    html += '<div style="font-size:13px;color:var(--utad-muted)">' + escapeHtml(d.email) + '</div></div>';
                    html += statusBadge + '</div>';

                    html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Status Akun</span><span class="ut-admin-detail-value">' +
                            (d.is_blocked ? 'Diblokir' : 'Aktif') + '</span></div>';
                    html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Email Verified</span><span class="ut-admin-detail-value">' +
                            (d.is_email_verified ? 'Ya' : 'Belum') + '</span></div>';
                    html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Telepon</span><span class="ut-admin-detail-value">' +
                            escapeHtml(d.phone || '-') + '</span></div>';
                    html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Bergabung</span><span class="ut-admin-detail-value">' +
                            escapeHtml(d.create_date || '-') + '</span></div>';
                    html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Status Seller</span><span class="ut-admin-detail-value">' +
                            escapeHtml(sellerStatusLabel) + '</span></div>';
                    if (seller.nim) {
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">NIM</span><span class="ut-admin-detail-value" style="font-family:monospace">' +
                                escapeHtml(seller.nim) + '</span></div>';
                    }
                    if (d.block_reason) {
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Alasan Blokir</span><span class="ut-admin-detail-value" style="color:var(--utad-red)">' +
                                escapeHtml(d.block_reason) + '</span></div>';
                    }

                    html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Total Order (Buyer)</span><span class="ut-admin-detail-value">' +
                            (stats.orders || 0) + ' transaksi · Rp ' + (stats.orders_total || '0') + '</span></div>';
                    html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Total Produk</span><span class="ut-admin-detail-value">' +
                            (stats.products || 0) + ' produk</span></div>';

                    if (d.ktm && d.ktm.has_record) {
                        var ktm = d.ktm;
                        var confidence = Number(ktm.confidence || 0);
                        var barWidth = Math.max(0, Math.min(100, confidence));
                        html += '<div class="ut-admin-modal-section">';
                        html += '<div class="ut-admin-modal-section-title">Verifikasi KTM</div>';
                        html += '<div class="ut-admin-ktm-panel">';
                        html += '<div class="ut-admin-ktm-info">';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Nama Penjual</span><span class="ut-admin-detail-value">' +
                                escapeHtml(ktm.seller_name || d.name || '-') + '</span></div>';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">NIM</span><span class="ut-admin-detail-value" style="font-family:monospace">' +
                                escapeHtml(ktm.nim || '-') + '</span></div>';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Status Verifikasi</span><span class="ut-admin-detail-value">' +
                                escapeHtml(ktm.state_label || '-') + '</span></div>';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">OCR Confidence</span><span class="ut-admin-detail-value">' +
                                '<span class="ut-admin-ktm-score"><span class="ut-admin-ktm-score-track"><span class="ut-admin-ktm-score-fill" style="width:' +
                                barWidth + '%"></span></span><strong>' + escapeHtml(confidence.toFixed(confidence % 1 ? 1 : 0)) + '%</strong></span></span></div>';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">NIM Match</span><span class="ut-admin-detail-value">' +
                                (ktm.nim_match ? 'Ya' : 'Belum') + '</span></div>';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Name Match</span><span class="ut-admin-detail-value">' +
                                (ktm.name_match ? 'Ya' : 'Belum') + '</span></div>';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Created On</span><span class="ut-admin-detail-value">' +
                                escapeHtml(ktm.created_on || '-') + '</span></div>';
                        html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Tanggal Verifikasi</span><span class="ut-admin-detail-value">' +
                                escapeHtml(ktm.verified_on || '-') + '</span></div>';
                        if (ktm.rejection_reason) {
                            html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Alasan Tolak</span><span class="ut-admin-detail-value" style="color:var(--utad-red)">' +
                                    escapeHtml(ktm.rejection_reason) + '</span></div>';
                        }
                        html += '</div>';
                        html += '<div class="ut-admin-ktm-preview">';
                        if (ktm.has_image && ktm.image_url) {
                            html += '<a href="' + escapeHtml(ktm.image_url) + '" target="_blank" rel="noopener" class="ut-admin-ktm-image-link">';
                            html += '<img src="' + escapeHtml(ktm.image_url) + '" alt="Foto KTM ' + escapeHtml(ktm.seller_name || d.name || '') + '"/>';
                            html += '</a>';
                            html += '<div class="ut-admin-ktm-caption">' + escapeHtml(ktm.filename || 'Foto KTM') + '</div>';
                        } else {
                            html += '<div class="ut-admin-ktm-empty">Foto KTM belum tersedia.</div>';
                        }
                        html += '</div>';
                        html += '</div>';
                        if (ktm.is_pending && (ktm.verification_id || ktm.seller_id)) {
                            html += '<div style="display:flex;gap:8px;margin-top:12px">';
                            html += '<button type="button" class="ut-admin-btn ut-admin-btn-success ut-admin-btn-sm" data-action="approve-seller"' +
                                    (ktm.seller_id ? ' data-seller-id="' + escapeHtml(ktm.seller_id) + '"' : '') +
                                    (ktm.verification_id ? ' data-verification-id="' + escapeHtml(ktm.verification_id) + '"' : '') +
                                    '>Approve KTM</button>';
                            html += '<button type="button" class="ut-admin-btn ut-admin-btn-danger ut-admin-btn-sm" data-action="reject-seller"' +
                                    (ktm.seller_id ? ' data-seller-id="' + escapeHtml(ktm.seller_id) + '"' : '') +
                                    (ktm.verification_id ? ' data-verification-id="' + escapeHtml(ktm.verification_id) + '"' : '') +
                                    '>Tolak KTM</button>';
                            html += '</div>';
                        } else if (ktm.is_verified && ktm.seller_id) {
                            html += '<div style="margin-top:12px">';
                            html += '<button type="button" class="ut-admin-btn ut-admin-btn-danger ut-admin-btn-sm" data-action="revoke-seller" data-seller-id="' +
                                    escapeHtml(ktm.seller_id) + '">Lepas Status Seller</button>';
                            html += '</div>';
                        }
                        html += '</div>';
                    }

                    // Admin note
                    html += '<div class="ut-admin-modal-section">';
                    html += '<div class="ut-admin-modal-section-title">Catatan Internal Admin</div>';
                    html += '<textarea class="ut-admin-textarea" id="utAdminUserNote" placeholder="Catatan internal yang tidak terlihat user...">' +
                            escapeHtml(d.admin_note || '') + '</textarea>';
                    html += '<div style="display:flex;gap:8px;margin-top:10px">';
                    html += '<button type="button" class="ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm" data-action="save-user-note" data-user-id="' +
                            d.id + '">Simpan Catatan</button>';
                    html += '<button type="button" class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" data-action="resend-otp" data-user-id="' +
                            d.id + '">Kirim Ulang OTP</button>';
                    html += '</div></div>';

                    // Audit log
                    if (d.audit_log && d.audit_log.length) {
                        html += '<div class="ut-admin-modal-section">';
                        html += '<div class="ut-admin-modal-section-title">Riwayat Tindakan Admin</div>';
                        html += '<div class="ut-admin-log-list">';
                        d.audit_log.forEach(function (log) {
                            html += '<div class="ut-admin-log-item">';
                            html += '<div class="ut-admin-log-meta">' + escapeHtml(log.date) + ' · ' + escapeHtml(log.author || 'Sistem') + '</div>';
                            html += '<div>' + log.body + '</div>';
                            html += '</div>';
                        });
                        html += '</div></div>';
                    }

                    body.innerHTML = html;
                });
        }

        function openOrderDetail(orderId) {
            var body = document.getElementById("utAdminOrderModalBody");
            if (!body) return;
            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminOrderModal");
            callJsonRpc("/unitrade/admin/api/orders/detail", { order_id: orderId })
                .then(function (res) {
                    var d = res.result || {};
                    var escrow = d.escrow || {};
                    var refund = d.refund || {};
                    var payout = d.payout || {};
                    var html = '';
                    var badgeClassByTone = {
                        green: "ut-admin-badge-green",
                        yellow: "ut-admin-badge-yellow",
                        red: "ut-admin-badge-red",
                        blue: "ut-admin-badge-blue",
                        gray: "ut-admin-badge-gray",
                    };

                    function badge(text, color) {
                        if (!text) return "";
                        return '<span class="ut-admin-badge ' + (badgeClassByTone[color] || "ut-admin-badge-gray") + '">' +
                            escapeHtml(text) + '</span>';
                    }

                    function detailRow(label, value, strong) {
                        return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                            escapeHtml(label) + '</span><span class="ut-admin-detail-value"' +
                            (strong ? ' style="font-weight:700"' : '') + '>' +
                            escapeHtml(value || "-") + '</span></div>';
                    }

                    function section(title, content) {
                        if (!content) return "";
                        return '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">' +
                            escapeHtml(title) + '</div>' + content + '</div>';
                    }

                    html += '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px">';
                    html += '<span style="font-family:monospace;font-size:13px">' + escapeHtml(d.name || '') + '</span>';
                    html += badge(d.state_label || "", "blue");
                    html += badge(d.unitrade_state_label || "", "gray");
                    html += badge(d.payment_status_label || "", d.payment_status === "paid" ? "green" : "yellow");
                    html += badge(d.escrow_state_label || "", d.escrow_state === "disputed" ? "red" : "blue");
                    if (d.is_flagged) {
                        html += badge("Bermasalah", "red");
                    }
                    html += '</div>';

                    html += detailRow("Buyer", (d.buyer_name || "-") + (d.buyer_email ? " (" + d.buyer_email + ")" : ""));
                    html += detailRow("Seller", d.seller_name || "-");
                    html += detailRow("Nominal", d.amount_display, true);
                    html += detailRow("Waktu Order", d.create_date);

                    var paymentHtml = "";
                    paymentHtml += detailRow("Provider", d.payment_provider_label || "-");
                    paymentHtml += detailRow("Metode", d.payment_method || "-");
                    paymentHtml += detailRow("Status Intent", d.payment_intent_state_label || d.payment_status_label || "-");
                    paymentHtml += detailRow("Referensi", d.payment_reference || d.payment_intent_name || "-");
                    if (d.payment_paid_at) paymentHtml += detailRow("Dibayar Pada", d.payment_paid_at);
                    if (d.payment_expires_at) paymentHtml += detailRow("Expired Pembayaran", d.payment_expires_at);
                    html += section("Pembayaran", paymentHtml);

                    var escrowHtml = "";
                    escrowHtml += detailRow("Status Escrow", escrow.state_label || d.escrow_state_label || "-");
                    escrowHtml += detailRow("Jumlah Ledger", escrow.count ? String(escrow.count) : "0");
                    escrowHtml += detailRow("Dana Seller", escrow.total_seller_display || "Rp 0", true);
                    if (escrow.rows && escrow.rows.length) {
                        escrowHtml += '<div class="ut-admin-log-list" style="margin-top:10px">';
                        escrow.rows.forEach(function (row) {
                            escrowHtml += '<div class="ut-admin-log-item">';
                            escrowHtml += '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">';
                            escrowHtml += '<strong>' + escapeHtml(row.name || "Ledger") + '</strong>';
                            escrowHtml += badge(row.state_label || "", row.state === "disputed" ? "red" : "blue");
                            escrowHtml += '</div>';
                            escrowHtml += '<div class="ut-admin-log-meta">' +
                                escapeHtml(row.seller_name || "-") + ' · ' +
                                escapeHtml(row.amount_seller_display || "Rp 0") + ' · Payout: ' +
                                escapeHtml(row.payout_status_label || "-") + '</div>';
                            escrowHtml += '</div>';
                        });
                        escrowHtml += '</div>';
                    }
                    html += section("Escrow", escrowHtml);

                    var mediationHtml = "";
                    mediationHtml += detailRow("Status Refund", refund.state_label || "-");
                    mediationHtml += detailRow("Kasus Refund", refund.latest_name || "-");
                    mediationHtml += detailRow("Admin Penengah", refund.admin_name || "-");
                    if (refund.requested_amount_display) mediationHtml += detailRow("Nominal Diajukan", refund.requested_amount_display);
                    if (refund.approved_amount_display) mediationHtml += detailRow("Nominal Disetujui", refund.approved_amount_display);
                    mediationHtml += detailRow("Status Payout", payout.latest_state_label || "-");
                    if (payout.latest_name) mediationHtml += detailRow("Batch Payout", payout.latest_name);
                    if (payout.total_amount_display) mediationHtml += detailRow("Nominal Payout", payout.total_amount_display);
                    html += section("Refund & Payout", mediationHtml);

                    if (d.lines && d.lines.length) {
                        var itemHtml = "";
                        d.lines.forEach(function (line) {
                            itemHtml += '<div class="ut-admin-detail-row">';
                            itemHtml += '<span class="ut-admin-detail-label">' + escapeHtml(line.qty) + 'x</span>';
                            itemHtml += '<span class="ut-admin-detail-value">' + escapeHtml(line.name) +
                                ' <span style="color:var(--utad-muted);float:right">Rp ' + escapeHtml(line.subtotal) + '</span></span>';
                            itemHtml += '</div>';
                        });
                        html += section("Item", itemHtml);
                    }

                    if (d.is_flagged && d.flag_reason) {
                        html += '<div class="ut-admin-modal-section">';
                        html += '<div class="ut-admin-modal-section-title" style="color:var(--utad-red)">Alasan Flag</div>';
                        html += '<div style="background:var(--utad-red-light);padding:10px;border-radius:6px;font-size:13px">' +
                                escapeHtml(d.flag_reason) + '</div>';
                        html += '</div>';
                    }

                    if (d.status_steps && d.status_steps.length) {
                        var statusHtml = '<div class="ut-admin-log-list">';
                        d.status_steps.forEach(function (step) {
                            statusHtml += '<div class="ut-admin-log-item">';
                            statusHtml += '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">';
                            statusHtml += '<strong>' + escapeHtml(step.title || "-") + '</strong>';
                            statusHtml += badge(step.status || "", step.tone || "gray");
                            statusHtml += '</div>';
                            statusHtml += '<div class="ut-admin-log-meta">' + escapeHtml(step.date || "-") + '</div>';
                            if (step.note) {
                                statusHtml += '<div style="font-size:13px;color:var(--utad-text-2);margin-top:4px">' +
                                    escapeHtml(step.note) + '</div>';
                            }
                            statusHtml += '</div>';
                        });
                        statusHtml += '</div>';
                        html += section("Riwayat Status", statusHtml);
                    }

                    if (d.payment_events && d.payment_events.length) {
                        var eventHtml = '<div class="ut-admin-log-list">';
                        d.payment_events.forEach(function (event) {
                            eventHtml += '<div class="ut-admin-log-item">';
                            eventHtml += '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">';
                            eventHtml += '<strong>' + escapeHtml(event.event_key || "Payment Event") + '</strong>';
                            eventHtml += badge(event.state_label || "", event.state_label === "Failed" ? "red" : "gray");
                            eventHtml += '</div>';
                            eventHtml += '<div class="ut-admin-log-meta">' +
                                escapeHtml(event.date || "-") + ' · ' + escapeHtml(event.provider || "-") + '</div>';
                            eventHtml += '</div>';
                        });
                        eventHtml += '</div>';
                        html += section("Event Pembayaran", eventHtml);
                    }

                    if (d.timeline && d.timeline.length) {
                        var chatterHtml = '<div class="ut-admin-log-list">';
                        d.timeline.forEach(function (log) {
                            chatterHtml += '<div class="ut-admin-log-item">';
                            chatterHtml += '<div class="ut-admin-log-meta">' + escapeHtml(log.date) + ' · ' + escapeHtml(log.author || 'Sistem') + '</div>';
                            if (log.subject) chatterHtml += '<div style="font-weight:600">' + escapeHtml(log.subject) + '</div>';
                            chatterHtml += '<div>' + log.body + '</div>';
                            chatterHtml += '</div>';
                        });
                        chatterHtml += '</div>';
                        html += section("Catatan Sistem", chatterHtml);
                    }

                    // Footer actions
                    html += '<div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">';
                    if (d.is_flagged) {
                        html += '<button type="button" class="ut-admin-btn ut-admin-btn-success ut-admin-btn-sm" data-action="unflag-order" data-order-id="' +
                                d.id + '">Hapus Tanda Bermasalah</button>';
                    } else {
                        html += '<button type="button" class="ut-admin-btn ut-admin-btn-danger ut-admin-btn-sm" data-action="flag-order" data-order-id="' +
                                d.id + '">Tandai Bermasalah</button>';
                    }
                    html += '</div>';

                    body.innerHTML = html;
                });
        }

        function openProductDetail(productId) {
            var body = document.getElementById("utAdminProductModalBody");
            if (!body) return;
            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminProductModal");
            callJsonRpc("/unitrade/admin/api/products/detail", { product_id: productId })
                .then(function (res) {
                    var d = res.result || {};
                    if (!d.ok) {
                        body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                            escapeHtml(d.error || "Produk tidak ditemukan.") + '</div>';
                        return;
                    }

                    function badge(text, color) {
                        if (!text) return "";
                        return '<span class="ut-admin-badge ut-admin-badge-' + escapeHtml(color || "gray") + '">' +
                            '<span class="ut-admin-badge-dot"></span>' + escapeHtml(text) + '</span>';
                    }

                    function row(label, value) {
                        return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                            escapeHtml(label) + '</span><span class="ut-admin-detail-value">' +
                            escapeHtml(value || "-") + '</span></div>';
                    }

                    function section(title, content) {
                        if (!content) return "";
                        return '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">' +
                            escapeHtml(title) + '</div>' + content + '</div>';
                    }

                    function productAction(label, productActionName, cssClass, extraAttrs) {
                        return '<button type="button" class="' + escapeHtml(cssClass) + '" ' +
                            'data-action="product-action" data-product-id="' + escapeHtml(d.id) + '" ' +
                            'data-product-action="' + escapeHtml(productActionName) + '" ' +
                            (extraAttrs || "") + '>' + escapeHtml(label) + '</button>';
                    }

                    var html = '';
                    var images = d.images || [];
                    var actions = d.actions || {};

                    html += '<div class="ut-admin-product-detail-head">';
                    html += '<div>';
                    html += '<div class="ut-admin-product-detail-title">' + escapeHtml(d.name || "-") + '</div>';
                    html += '<div class="ut-admin-product-detail-meta">' +
                        escapeHtml(d.default_code || d.category || "-") + '</div>';
                    html += '</div>';
                    html += '<div class="ut-admin-product-detail-badges">';
                    html += badge(d.listing_status_label, d.listing_badge_class);
                    html += badge(d.fee_status_label, d.fee_badge_class);
                    html += '</div>';
                    html += '</div>';

                    html += '<div class="ut-admin-product-detail-grid">';
                    html += '<div>';
                    html += '<div class="ut-admin-product-detail-gallery">';
                    images.forEach(function (image) {
                        html += '<a href="' + escapeHtml(image.url) + '" target="_blank" rel="noopener" ' +
                            'class="ut-admin-product-detail-image">';
                        html += '<img src="' + escapeHtml(image.url) + '" alt="' + escapeHtml(image.label || d.name) + '"/>';
                        html += '<span>' + escapeHtml(image.label || "Foto Produk") + '</span>';
                        html += '</a>';
                    });
                    html += '</div>';
                    html += section("Deskripsi Produk",
                        '<p class="ut-admin-product-detail-description">' + escapeHtml(d.description || "-") + '</p>');
                    html += '</div>';

                    html += '<div>';
                    var infoHtml = "";
                    infoHtml += row("Harga", d.price);
                    infoHtml += row("Stok", d.stock);
                    infoHtml += row("Kategori", d.category);
                    infoHtml += row("Kondisi", d.condition);
                    infoHtml += row("Brand", d.brand);
                    infoHtml += row("Aktif Listing", d.activated_at);
                    infoHtml += row("Expired Listing", d.expires_at);
                    infoHtml += row("Biaya Listing", d.listing_fee);
                    infoHtml += row("Fee Dibayar", d.fee_paid_at);
                    html += section("Informasi Listing", infoHtml);

                    var sellerHtml = "";
                    sellerHtml += row("Nama Seller", d.seller && d.seller.name);
                    sellerHtml += row("Status Seller", d.seller && d.seller.status);
                    sellerHtml += row("Email", d.seller && d.seller.email);
                    sellerHtml += row("NIM", d.seller && d.seller.nim);
                    if (d.seller && d.seller.admin_user_url) {
                        sellerHtml += '<div style="display:flex;justify-content:flex-end;margin-top:10px">' +
                            '<a href="' + escapeHtml(d.seller.admin_user_url) + '" class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-xs">' +
                            'Buka User</a></div>';
                    }
                    html += section("Seller", sellerHtml);

                    if (d.waive_reason || d.rejection_reason || actions.publish_blocked_reason) {
                        var noteHtml = "";
                        if (actions.publish_blocked_reason) noteHtml += row("Catatan Fee", actions.publish_blocked_reason);
                        if (d.waive_reason) noteHtml += row("Alasan Waive", d.waive_reason);
                        if (d.rejection_reason) noteHtml += row("Alasan Tolak", d.rejection_reason);
                        html += section("Catatan Admin", noteHtml);
                    }

                    var actionHtml = '<div class="ut-admin-product-detail-actions">';
                    if (actions.can_publish) {
                        actionHtml += productAction("Publish", "publish", "ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm");
                    }
                    if (actions.can_unpublish) {
                        actionHtml += productAction("Unpublish", "unpublish", "ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm");
                    }
                    if (actions.can_waive) {
                        actionHtml += productAction(
                            "Waive Fee & Publish",
                            "waive",
                            "ut-admin-btn ut-admin-btn-success ut-admin-btn-sm",
                            'data-publish-after="true"'
                        );
                    }
                    if (actions.can_reject) {
                        actionHtml += productAction("Tolak Listing", "reject", "ut-admin-btn ut-admin-btn-danger ut-admin-btn-sm");
                    }
                    if (d.public_url) {
                        actionHtml += '<a href="' + escapeHtml(d.public_url) + '" target="_blank" rel="noopener" ' +
                            'class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm">Lihat Publik</a>';
                    }
                    actionHtml += '</div>';
                    html += section("Aksi Admin", actionHtml);
                    html += '</div>';
                    html += '</div>';

                    var history = d.listing_fee_history || [];
                    if (history.length) {
                        var historyHtml = '<div class="ut-admin-log-list">';
                        history.forEach(function (intent) {
                            var tone = intent.state === "paid" ? "green"
                                : (intent.state === "failed" || intent.state === "expired" || intent.state === "cancelled") ? "red"
                                : "yellow";
                            historyHtml += '<div class="ut-admin-log-item">';
                            historyHtml += '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">';
                            historyHtml += '<strong>' + escapeHtml(intent.name || "Listing Fee") + '</strong>';
                            historyHtml += badge(intent.state_label || intent.state, tone);
                            historyHtml += '</div>';
                            historyHtml += '<div class="ut-admin-log-meta">' +
                                escapeHtml(intent.provider || "-") + ' · ' +
                                escapeHtml(intent.method || "-") + ' · ' +
                                escapeHtml(intent.amount || "Rp 0") + '</div>';
                            historyHtml += '<div style="font-size:12px;color:var(--utad-text-2)">Referensi: ' +
                                escapeHtml(intent.reference || "-") + '</div>';
                            historyHtml += '<div style="font-size:12px;color:var(--utad-muted);margin-top:4px">Dibuat: ' +
                                escapeHtml(intent.created || "-") + ' · Expired: ' +
                                escapeHtml(intent.expires_at || "-") + ' · Paid: ' +
                                escapeHtml(intent.paid_at || "-") + '</div>';
                            if (intent.error) {
                                historyHtml += '<div style="font-size:12px;color:var(--utad-red);margin-top:4px">' +
                                    escapeHtml(intent.error) + '</div>';
                            }
                            historyHtml += '</div>';
                        });
                        historyHtml += '</div>';
                        html += section("Riwayat Listing Fee", historyHtml);
                    } else {
                        html += section("Riwayat Listing Fee",
                            '<div class="ut-admin-empty-inline">Belum ada pembayaran listing fee untuk produk ini.</div>');
                    }

                    body.innerHTML = html;
                })
                .catch(function () {
                    body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                        'Gagal memuat detail produk.</div>';
                });
        }

        function openAnnouncementDetail(announcementId, sourceButton) {
            var body = document.getElementById("utAdminAnnouncementDetailBody");
            if (!body) return;

            function row(label, value) {
                return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                    escapeHtml(label) + '</span><span class="ut-admin-detail-value">' +
                    escapeHtml(value || "-") + '</span></div>';
            }

            function section(title, content) {
                return '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">' +
                    escapeHtml(title) + '</div>' + content + '</div>';
            }

            function datasetFallback() {
                if (!sourceButton || !sourceButton.dataset.annTitle) return null;
                return {
                    ok: true,
                    id: announcementId,
                    title: sourceButton.dataset.annTitle,
                    body: sourceButton.dataset.annBody,
                    action_url: sourceButton.dataset.annActionUrl,
                    state_label: sourceButton.dataset.annStateLabel,
                    badge_class: sourceButton.dataset.annBadgeClass,
                    created: "-",
                    published_at: sourceButton.dataset.annPublishedAt,
                    published_by: sourceButton.dataset.annPublishedBy,
                    target_user_count: sourceButton.dataset.annTargetCount,
                    emitted_count: sourceButton.dataset.annEmittedCount,
                    failed_batches: sourceButton.dataset.annFailedCount,
                    notification_stats: {
                        total: sourceButton.dataset.annEmittedCount,
                        unread: "-",
                        read: "-",
                    },
                };
            }

            function renderDetail(d, partial) {
                var stats = d.notification_stats || {};
                var html = '';
                html += '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-bottom:14px">';
                html += '<div><div class="ut-admin-product-detail-title">' + escapeHtml(d.title || "-") + '</div>';
                html += '<div class="ut-admin-product-detail-meta">Dibuat: ' + escapeHtml(d.created || "-") + '</div></div>';
                html += '<span class="ut-admin-badge ut-admin-badge-' + escapeHtml(d.badge_class || "gray") + '">' +
                    escapeHtml(d.state_label || "-") + '</span>';
                html += '</div>';

                if (partial) {
                    html += '<div class="ut-admin-empty-inline" style="margin-bottom:12px">' +
                        'Detail ditampilkan dari data tabel admin.' +
                        '</div>';
                }

                html += section("Isi Pengumuman",
                    '<p class="ut-admin-product-detail-description">' + escapeHtml(d.body || "-") + '</p>');

                var broadcastHtml = "";
                broadcastHtml += row("Target saat publish", d.target_user_count);
                broadcastHtml += row("Notifikasi tersedia", stats.total || d.emitted_count);
                broadcastHtml += row("Belum dibaca", stats.unread);
                broadcastHtml += row("Sudah dibaca", stats.read);
                broadcastHtml += row("Batch gagal", d.failed_batches);
                html += section("Status Notifikasi User", broadcastHtml);

                var metaHtml = "";
                metaHtml += row("Link aksi user", d.action_url);
                metaHtml += row("Dipublish pada", d.published_at);
                metaHtml += row("Dipublish oleh", d.published_by);
                html += section("Informasi", metaHtml);

                body.innerHTML = html;
            }

            var fallback = datasetFallback();
            if (fallback) {
                renderDetail(fallback, true);
            } else {
                body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            }
            openModal("utAdminAnnouncementDetailModal");

            callJsonRpc("/unitrade/admin/api/announcements/detail", { announcement_id: announcementId })
                .then(function (res) {
                    var d = res.result || {};
                    if (d.ok) {
                        renderDetail(d, false);
                    } else if (!fallback) {
                        body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                            escapeHtml(d.error || "Pengumuman tidak ditemukan.") + '</div>';
                    }
                })
                .catch(function () {
                    if (!fallback) {
                        body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                            'Gagal memuat detail pengumuman.</div>';
                    }
                });
        }

        function openCustomerServiceDetail(caseType, caseId) {
            var body = document.getElementById("utAdminCsCaseModalBody");
            if (!body) return;

            function badge(text, tone) {
                return '<span class="ut-admin-badge ut-admin-badge-' + escapeHtml(tone || "gray") + '">' +
                    '<span class="ut-admin-badge-dot"></span>' + escapeHtml(text || "-") + '</span>';
            }

            function row(label, value) {
                return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                    escapeHtml(label || "-") + '</span><span class="ut-admin-detail-value">' +
                    escapeHtml(value == null || value === "" ? "-" : value) + '</span></div>';
            }

            function section(title, content) {
                if (!content) return "";
                return '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">' +
                    escapeHtml(title || "-") + '</div>' + content + '</div>';
            }

            function mediaGrid(items) {
                items = items || [];
                if (!items.length) {
                    return '<div class="ut-admin-empty-inline">Belum ada bukti gambar atau lampiran.</div>';
                }
                var html = '<div class="ut-admin-cs-media-grid">';
                items.forEach(function (item) {
                    var caption = escapeHtml(item.name || item.label || "Bukti");
                    var meta = [item.mimetype, item.size_label].filter(Boolean).join(" · ");
                    html += '<div class="ut-admin-cs-media-item">';
                    if (item.is_image) {
                        html += '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener" class="ut-admin-cs-media-preview">';
                        html += '<img src="' + escapeHtml(item.url) + '" alt="' + caption + '"/>';
                        html += '</a>';
                    } else if (item.is_video) {
                        html += '<video class="ut-admin-cs-media-preview" src="' + escapeHtml(item.url) + '" controls></video>';
                    } else {
                        html += '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener" class="ut-admin-cs-file-preview">';
                        html += '<i class="fa fa-paperclip" aria-hidden="true"></i><span>Lihat lampiran</span></a>';
                    }
                    html += '<div class="ut-admin-cs-media-caption">' + caption + '</div>';
                    if (meta) html += '<div class="ut-admin-cs-media-meta">' + escapeHtml(meta) + '</div>';
                    if (item.note) html += '<div class="ut-admin-cs-media-note">' + escapeHtml(item.note) + '</div>';
                    html += '</div>';
                });
                html += '</div>';
                return html;
            }

            function renderDetail(d) {
                var html = '';
                html += '<div class="ut-admin-cs-detail-head">';
                html += '<div><div class="ut-admin-product-detail-title">' + escapeHtml(d.title || "-") + '</div>';
                html += '<div class="ut-admin-product-detail-meta">' + escapeHtml(d.type_label || "Laporan") + '</div></div>';
                html += '<div class="ut-admin-product-detail-badges">' +
                    badge(d.status || "-", d.urgency === "urgent" ? "red" : "yellow") + '</div>';
                html += '</div>';

                var infoHtml = "";
                (d.rows || []).forEach(function (item) {
                    infoHtml += row(item.label, item.value);
                });
                html += section("Informasi Kasus", infoHtml);

                if (d.description) {
                    html += section("Isi Laporan",
                        '<p class="ut-admin-product-detail-description">' + escapeHtml(d.description) + '</p>');
                }

                html += section("Bukti / Media", mediaGrid(d.evidence || []));

                if (d.messages && d.messages.length) {
                    var messageHtml = '<div class="ut-admin-cs-message-list">';
                    d.messages.forEach(function (message) {
                        messageHtml += '<div class="ut-admin-cs-message">';
                        messageHtml += '<div class="ut-admin-cs-message-meta">' +
                            escapeHtml(message.author || "-") + ' · ' + escapeHtml(message.time || "-") +
                            ' · ' + escapeHtml(message.type || "-") + '</div>';
                        if (message.body) {
                            messageHtml += '<div class="ut-admin-cs-message-body">' + escapeHtml(message.body) + '</div>';
                        }
                        if (message.media) {
                            messageHtml += mediaGrid([message.media]);
                        }
                        messageHtml += '</div>';
                    });
                    messageHtml += '</div>';
                    html += section(d.type === "ticket" ? "Thread Bantuan" : "Cuplikan Chat", messageHtml);
                }

                if (d.notes && d.notes.length) {
                    var notesHtml = '<div class="ut-admin-log-list">';
                    d.notes.forEach(function (note) {
                        notesHtml += '<div class="ut-admin-log-item">';
                        notesHtml += '<div class="ut-admin-log-meta">' + escapeHtml(note.label || "Catatan") + '</div>';
                        notesHtml += '<div>' + escapeHtml(note.value || "-") + '</div>';
                        notesHtml += '</div>';
                    });
                    notesHtml += '</div>';
                    html += section("Catatan", notesHtml);
                }

                if (d.timeline && d.timeline.length) {
                    var timelineHtml = '<div class="ut-admin-log-list">';
                    d.timeline.forEach(function (item) {
                        timelineHtml += '<div class="ut-admin-log-item">';
                        timelineHtml += '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">';
                        timelineHtml += '<strong>' + escapeHtml(item.title || "-") + '</strong>';
                        if (item.status) timelineHtml += badge(item.status, "blue");
                        timelineHtml += '</div>';
                        timelineHtml += '<div class="ut-admin-log-meta">' + escapeHtml(item.time || item.date || "-") + '</div>';
                        if (item.note) timelineHtml += '<div>' + escapeHtml(item.note) + '</div>';
                        timelineHtml += '</div>';
                    });
                    timelineHtml += '</div>';
                    html += section("Timeline", timelineHtml);
                }

                if (d.actions && (d.actions.can_reply || d.actions.can_start || d.actions.can_done || d.actions.refund_url)) {
                    var actionHtml = '<div class="ut-admin-product-detail-actions">';
                    if (d.actions.can_reply) {
                        actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm" ' +
                            'data-action="ticket-reply" data-ticket-id="' + escapeHtml(d.actions.ticket_id) + '">Balas User</button>';
                    }
                    if (d.actions.can_start) {
                        actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" ' +
                            'data-action="ticket-status" data-ticket-id="' + escapeHtml(d.actions.ticket_id) + '" ' +
                            'data-status="in_progress">Proses Tiket</button>';
                    }
                    if (d.actions.can_done) {
                        actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm" ' +
                            'data-action="ticket-status" data-ticket-id="' + escapeHtml(d.actions.ticket_id) + '" ' +
                            'data-status="done">Selesaikan Tiket</button>';
                    }
                    if (d.actions.refund_url) {
                        actionHtml += '<a class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" ' +
                            'href="' + escapeHtml(d.actions.refund_url) + '" target="_blank" rel="noopener">' +
                            escapeHtml(d.actions.refund_label || "Buka Refund") + '</a>';
                    }
                    actionHtml += '</div>';
                    html += section("Aksi Admin", actionHtml);
                }

                body.innerHTML = html;
            }

            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminCsCaseModal");
            callJsonRpc("/unitrade/admin/api/customer-service/detail", {
                case_type: caseType,
                case_id: caseId,
            }).then(function (res) {
                var d = res.result || {};
                if (d.ok) {
                    renderDetail(d);
                } else {
                    body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                        escapeHtml(d.error || "Laporan tidak ditemukan.") + '</div>';
                }
            }).catch(function () {
                body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                    'Gagal memuat detail laporan.</div>';
            });
        }

        function openReportDetail(reportType, reportId) {
            var body = document.getElementById("utAdminReportModalBody");
            if (!body) return;

            function badge(text, tone) {
                return '<span class="ut-admin-badge ut-admin-badge-' + escapeHtml(tone || "gray") + '">' +
                    '<span class="ut-admin-badge-dot"></span>' + escapeHtml(text || "-") + '</span>';
            }
            function row(label, value) {
                return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                    escapeHtml(label || "-") + '</span><span class="ut-admin-detail-value">' +
                    escapeHtml(value == null || value === "" ? "-" : value) + '</span></div>';
            }
            function section(title, content) {
                if (!content) return "";
                return '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">' +
                    escapeHtml(title || "-") + '</div>' + content + '</div>';
            }
            function mediaGrid(items) {
                items = items || [];
                if (!items.length) {
                    return '<div class="ut-admin-empty-inline">Belum ada bukti gambar atau lampiran.</div>';
                }
                var html = '<div class="ut-admin-cs-media-grid">';
                items.forEach(function (item) {
                    var caption = escapeHtml(item.name || item.label || "Bukti");
                    var meta = [item.mimetype, item.size_label].filter(Boolean).join(" · ");
                    html += '<div class="ut-admin-cs-media-item">';
                    if (item.is_image) {
                        html += '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener" class="ut-admin-cs-media-preview">';
                        html += '<img src="' + escapeHtml(item.url) + '" alt="' + caption + '"/></a>';
                    } else if (item.is_video) {
                        html += '<video class="ut-admin-cs-media-preview" src="' + escapeHtml(item.url) + '" controls></video>';
                    } else {
                        html += '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener" class="ut-admin-cs-file-preview">';
                        html += '<i class="fa fa-paperclip" aria-hidden="true"></i><span>Lihat lampiran</span></a>';
                    }
                    html += '<div class="ut-admin-cs-media-caption">' + caption + '</div>';
                    if (meta) html += '<div class="ut-admin-cs-media-meta">' + escapeHtml(meta) + '</div>';
                    if (item.note) html += '<div class="ut-admin-cs-media-note">' + escapeHtml(item.note) + '</div>';
                    html += '</div>';
                });
                html += '</div>';
                return html;
            }

            function renderDetail(d) {
                var html = '';
                html += '<div class="ut-admin-cs-detail-head">';
                html += '<div><div class="ut-admin-product-detail-title">' + escapeHtml(d.title || "-") + '</div>';
                html += '<div class="ut-admin-product-detail-meta">' + escapeHtml(d.type_label || "Laporan") + '</div></div>';
                html += '<div class="ut-admin-product-detail-badges">' +
                    badge(d.status || "-", d.urgency === "urgent" ? "red" : "yellow") + '</div>';
                html += '</div>';

                var infoHtml = "";
                (d.rows || []).forEach(function (item) { infoHtml += row(item.label, item.value); });
                html += section("Informasi Laporan", infoHtml);

                if (d.description) {
                    html += section("Isi Laporan",
                        '<p class="ut-admin-product-detail-description">' + escapeHtml(d.description) + '</p>');
                }

                html += section("Bukti / Media", mediaGrid(d.evidence || []));

                if (d.messages && d.messages.length) {
                    var messageHtml = '<div class="ut-admin-cs-message-list">';
                    d.messages.forEach(function (message) {
                        messageHtml += '<div class="ut-admin-cs-message">';
                        messageHtml += '<div class="ut-admin-cs-message-meta">' +
                            escapeHtml(message.author || "-") + ' · ' + escapeHtml(message.time || "-") + '</div>';
                        if (message.body) {
                            messageHtml += '<div class="ut-admin-cs-message-body">' + escapeHtml(message.body) + '</div>';
                        }
                        if (message.media) { messageHtml += mediaGrid([message.media]); }
                        messageHtml += '</div>';
                    });
                    messageHtml += '</div>';
                    html += section("Cuplikan", messageHtml);
                }

                if (d.notes && d.notes.length) {
                    var notesHtml = '<div class="ut-admin-log-list">';
                    d.notes.forEach(function (note) {
                        notesHtml += '<div class="ut-admin-log-item"><div class="ut-admin-log-meta">' +
                            escapeHtml(note.label || "Catatan") + '</div><div>' + escapeHtml(note.value || "-") + '</div></div>';
                    });
                    notesHtml += '</div>';
                    html += section("Catatan", notesHtml);
                }

                if (d.timeline && d.timeline.length) {
                    var timelineHtml = '<div class="ut-admin-log-list">';
                    d.timeline.forEach(function (item) {
                        timelineHtml += '<div class="ut-admin-log-item">';
                        timelineHtml += '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">';
                        timelineHtml += '<strong>' + escapeHtml(item.title || "-") + '</strong>';
                        if (item.status) timelineHtml += badge(item.status, "blue");
                        timelineHtml += '</div>';
                        timelineHtml += '<div class="ut-admin-log-meta">' + escapeHtml(item.time || item.date || "-") + '</div>';
                        if (item.note) timelineHtml += '<div>' + escapeHtml(item.note) + '</div>';
                        timelineHtml += '</div>';
                    });
                    timelineHtml += '</div>';
                    html += section("Timeline", timelineHtml);
                }

                var a = d.actions || {};
                var actionHtml = '';
                // Aksi tiket (reuse alur lama) untuk tipe ticket
                if (a.can_reply) {
                    actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm" ' +
                        'data-action="ticket-reply" data-ticket-id="' + escapeHtml(a.ticket_id) + '">Balas User</button>';
                }
                if (a.can_start) {
                    actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" ' +
                        'data-action="ticket-status" data-ticket-id="' + escapeHtml(a.ticket_id) + '" data-status="in_progress">Proses Tiket</button>';
                }
                if (a.can_done) {
                    actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm" ' +
                        'data-action="ticket-status" data-ticket-id="' + escapeHtml(a.ticket_id) + '" data-status="done">Selesaikan Tiket</button>';
                }
                if (a.refund_url) {
                    actionHtml += '<a class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" href="' +
                        escapeHtml(a.refund_url) + '" target="_blank" rel="noopener">' +
                        escapeHtml(a.refund_label || "Buka Refund") + '</a>';
                }
                // Aksi status laporan generik (chat/review/seller)
                if (a.report_status) {
                    actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" ' +
                        'data-action="report-set-status" data-report-type="' + escapeHtml(a.report_type) + '" ' +
                        'data-report-id="' + escapeHtml(a.report_id) + '" data-status="in_progress">Proses</button>';
                    actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-primary ut-admin-btn-sm" ' +
                        'data-action="report-set-status" data-report-type="' + escapeHtml(a.report_type) + '" ' +
                        'data-report-id="' + escapeHtml(a.report_id) + '" data-status="done">Selesaikan</button>';
                    if (a.can_reject) {
                        actionHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-danger ut-admin-btn-sm" ' +
                            'data-action="report-set-status" data-report-type="' + escapeHtml(a.report_type) + '" ' +
                            'data-report-id="' + escapeHtml(a.report_id) + '" data-status="rejected">Tolak</button>';
                    }
                }
                if (actionHtml) {
                    html += section("Aksi Admin", '<div class="ut-admin-product-detail-actions">' + actionHtml + '</div>');
                }

                body.innerHTML = html;
            }

            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminReportModal");
            callJsonRpc("/unitrade/admin/api/report-list/detail", {
                report_type: reportType,
                report_id: reportId,
            }).then(function (res) {
                var d = res.result || {};
                if (d.ok) {
                    renderDetail(d);
                } else {
                    body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                        escapeHtml(d.error || "Laporan tidak ditemukan.") + '</div>';
                }
            }).catch(function () {
                body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                    'Gagal memuat detail laporan.</div>';
            });
        }

        function openReviewDetail(reviewId) {
            var body = document.getElementById("utAdminReviewModalBody");
            if (!body) return;
            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminReviewModal");
            callJsonRpc("/unitrade/admin/api/reviews/detail", { review_id: reviewId }).then(function (res) {
                var d = res.result || {};
                if (!d.ok) {
                    body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                        escapeHtml(d.error || "Ulasan tidak ditemukan.") + '</div>';
                    return;
                }
                function row(label, value) {
                    return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                        escapeHtml(label) + '</span><span class="ut-admin-detail-value">' +
                        escapeHtml(value == null || value === "" ? "-" : value) + '</span></div>';
                }
                var html = '<div class="ut-admin-cs-detail-head">';
                html += '<div><div class="ut-admin-product-detail-title">' + escapeHtml(d.product) + '</div>';
                html += '<div class="ut-admin-product-detail-meta">Ulasan oleh ' + escapeHtml(d.reviewer) + '</div></div>';
                html += '<div class="ut-admin-product-detail-badges"><span class="ut-admin-badge ut-admin-badge-' +
                    escapeHtml(d.badge_class) + '"><span class="ut-admin-badge-dot"></span>' +
                    escapeHtml(d.visibility_label) + '</span></div></div>';

                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Informasi Ulasan</div>';
                html += row("Reviewer", d.reviewer);
                if (d.reviewer_email) html += row("Email", d.reviewer_email);
                html += row("Produk", d.product);
                html += row("Pesanan", d.order);
                html += row("Rating", d.rating_label + " (" + d.rating + "/5)");
                html += row("Tanggal", d.created);
                if (d.tags) html += row("Tag", d.tags);
                html += row("Membantu / Laporan", d.helpful_count + " membantu · " + d.report_count + " laporan");
                html += '</div>';

                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Komentar</div>' +
                    '<p class="ut-admin-product-detail-description">' + escapeHtml(d.comment || "(tanpa komentar)") + '</p></div>';

                if (d.images && d.images.length) {
                    var imgHtml = '<div class="ut-admin-cs-media-grid">';
                    d.images.forEach(function (src) {
                        imgHtml += '<div class="ut-admin-cs-media-item"><a href="' + escapeHtml(src) +
                            '" target="_blank" rel="noopener" class="ut-admin-cs-media-preview"><img src="' +
                            escapeHtml(src) + '" alt="Foto ulasan"/></a></div>';
                    });
                    imgHtml += '</div>';
                    html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Foto Ulasan</div>' + imgHtml + '</div>';
                }

                var actHtml = '<div class="ut-admin-product-detail-actions">';
                actHtml += '<button type="button" class="ut-admin-btn ut-admin-btn-' +
                    (d.is_visible ? 'danger' : 'success') + ' ut-admin-btn-sm" data-action="review-visibility" data-review-id="' +
                    escapeHtml(d.id) + '" data-visible="' + (d.is_visible ? 'false' : 'true') + '">' +
                    (d.is_visible ? 'Sembunyikan' : 'Tampilkan') + '</button>';
                if (d.product_url) {
                    actHtml += '<a class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm" href="' +
                        escapeHtml(d.product_url) + '" target="_blank" rel="noopener">Buka Produk</a>';
                }
                actHtml += '</div>';
                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Aksi Admin</div>' + actHtml + '</div>';

                body.innerHTML = html;
            }).catch(function () {
                body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">Gagal memuat detail ulasan.</div>';
            });
        }

        function openVoucherDetail(voucherId) {
            var body = document.getElementById("utAdminVoucherDetailBody");
            if (!body) return;
            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminVoucherDetailModal");
            callJsonRpc("/unitrade/admin/api/vouchers/detail", { voucher_id: voucherId }).then(function (res) {
                var d = res.result || {};
                if (!d.ok) {
                    body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                        escapeHtml(d.error || "Voucher tidak ditemukan.") + '</div>';
                    return;
                }
                function stat(label, value) {
                    return '<div class="ut-admin-stat-card" style="padding:14px">' +
                        '<div class="ut-admin-stat-label">' + escapeHtml(label) + '</div>' +
                        '<div class="ut-admin-stat-value" style="font-size:20px">' + escapeHtml(value) + '</div></div>';
                }
                var html = '<div class="ut-admin-cs-detail-head">';
                html += '<div><div class="ut-admin-product-detail-title">' + escapeHtml(d.code) + '</div>';
                html += '<div class="ut-admin-product-detail-meta">' + escapeHtml(d.name || '-') + ' · ' + escapeHtml(d.discount_label) + '</div></div>';
                html += '<div class="ut-admin-product-detail-badges"><span class="ut-admin-badge ut-admin-badge-' +
                    escapeHtml(d.badge_class) + '"><span class="ut-admin-badge-dot"></span>' + escapeHtml(d.status_label) + '</span></div></div>';

                html += '<div class="ut-admin-stats-grid" style="margin:12px 0">';
                html += stat("Total Kuota", d.usage_limit_label);
                html += stat("Sudah Dipakai", String(d.used_count));
                html += stat("Sisa Kuota", d.remaining_label);
                html += stat("Jumlah User", String(d.unique_users));
                html += stat("Total Diskon Diberikan", d.total_discount);
                html += stat("Limit / User", String(d.usage_limit_per_user || 'Tanpa batas'));
                html += '</div>';

                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Info Voucher</div>';
                html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Min. Order</span><span class="ut-admin-detail-value">' + escapeHtml(d.min_order_display) + '</span></div>';
                html += '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">Periode</span><span class="ut-admin-detail-value">' + escapeHtml(d.date_start_label) + ' s/d ' + escapeHtml(d.date_end_label) + '</span></div>';
                html += '</div>';

                var rowsHtml = '';
                if (d.usage_rows && d.usage_rows.length) {
                    rowsHtml += '<div class="ut-admin-table-wrapper"><table class="ut-admin-table"><thead><tr>' +
                        '<th>User</th><th>Order</th><th>Tanggal</th><th>Diskon</th><th>Total Order</th></tr></thead><tbody>';
                    d.usage_rows.forEach(function (u) {
                        rowsHtml += '<tr><td>' + escapeHtml(u.user) + '</td>' +
                            '<td><a href="' + escapeHtml(u.order_url) + '" target="_blank" rel="noopener">' + escapeHtml(u.order) + '</a></td>' +
                            '<td>' + escapeHtml(u.date) + '</td>' +
                            '<td>' + escapeHtml(u.discount) + '</td>' +
                            '<td>' + escapeHtml(u.amount_total) + '</td></tr>';
                    });
                    rowsHtml += '</tbody></table></div>';
                } else {
                    rowsHtml = '<div class="ut-admin-empty-inline">Voucher ini belum pernah digunakan.</div>';
                }
                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Riwayat Penggunaan</div>' + rowsHtml + '</div>';

                body.innerHTML = html;
            }).catch(function () {
                body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">Gagal memuat detail voucher.</div>';
            });
        }

        function openPayoutDetail(payoutId) {
            var body = document.getElementById("utAdminPayoutModalBody");
            if (!body) return;
            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminPayoutModal");
            callJsonRpc("/unitrade/admin/api/payouts/detail", { payout_id: payoutId }).then(function (res) {
                var d = res.result || {};
                if (!d.ok) {
                    body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                        escapeHtml(d.error || "Payout tidak ditemukan.") + '</div>';
                    return;
                }
                function row(label, value) {
                    return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                        escapeHtml(label) + '</span><span class="ut-admin-detail-value">' +
                        escapeHtml(value == null || value === "" ? "-" : value) + '</span></div>';
                }
                function stat(label, value) {
                    return '<div class="ut-admin-stat-card" style="padding:14px">' +
                        '<div class="ut-admin-stat-label">' + escapeHtml(label) + '</div>' +
                        '<div class="ut-admin-stat-value" style="font-size:18px">' + escapeHtml(value) + '</div></div>';
                }
                var html = '<div class="ut-admin-cs-detail-head">';
                html += '<div><div class="ut-admin-product-detail-title">' + escapeHtml(d.name) + '</div>';
                html += '<div class="ut-admin-product-detail-meta">Seller: ' + escapeHtml(d.seller) + ' · ' + escapeHtml(d.total_amount) + '</div></div>';
                html += '<div class="ut-admin-product-detail-badges"><span class="ut-admin-badge ut-admin-badge-' +
                    escapeHtml(d.badge_class) + '"><span class="ut-admin-badge-dot"></span>' + escapeHtml(d.state_label) + '</span></div></div>';

                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Saldo Seller (sinkron dengan dashboard seller)</div>';
                html += '<div class="ut-admin-stats-grid">';
                html += stat("Bisa Dicairkan", d.balance.payoutable);
                html += stat("Pending Payout", d.balance.pending);
                html += stat("Ditahan", d.balance.held);
                html += stat("Sudah Dicairkan", d.balance.released);
                html += '</div></div>';

                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Informasi Payout</div>';
                html += row("Total", d.total_amount);
                html += row("Jumlah Ledger", String(d.ledger_count));
                html += row("Channel / Bank", d.channel);
                html += row("Nama Rekening", d.account_name);
                html += row("Nomor Rekening", d.account_number);
                html += row("Referensi Pembayaran", d.payment_reference);
                html += row("Diminta", d.created);
                html += row("Dibayar", d.paid_at);
                if (d.cancel_reason) html += row("Alasan Batal", d.cancel_reason);
                html += '</div>';

                var ledgerHtml = '';
                if (d.ledger_rows && d.ledger_rows.length) {
                    ledgerHtml += '<div class="ut-admin-table-wrapper"><table class="ut-admin-table"><thead><tr>' +
                        '<th>Ledger</th><th>Order</th><th>Nominal Seller</th><th>State</th><th>Payout Status</th></tr></thead><tbody>';
                    d.ledger_rows.forEach(function (l) {
                        ledgerHtml += '<tr><td>' + escapeHtml(l.name) + '</td><td>' + escapeHtml(l.order) + '</td><td>' +
                            escapeHtml(l.amount) + '</td><td>' + escapeHtml(l.state) + '</td><td>' + escapeHtml(l.payout_status) + '</td></tr>';
                    });
                    ledgerHtml += '</tbody></table></div>';
                } else {
                    ledgerHtml = '<div class="ut-admin-empty-inline">Belum ada ledger pada payout ini.</div>';
                }
                html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Rincian Ledger</div>' + ledgerHtml + '</div>';

                if (d.history && d.history.length) {
                    var hHtml = '<div class="ut-admin-log-list">';
                    d.history.forEach(function (h) {
                        hHtml += '<div class="ut-admin-log-item"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">' +
                            '<strong>' + escapeHtml(h.name) + (h.is_current ? ' (ini)' : '') + ' · ' + escapeHtml(h.amount) + '</strong>' +
                            '<span class="ut-admin-badge ut-admin-badge-' + escapeHtml(h.badge_class) + '">' + escapeHtml(h.state_label) + '</span></div>' +
                            '<div class="ut-admin-log-meta">' + escapeHtml(h.created) + '</div></div>';
                    });
                    hHtml += '</div>';
                    html += '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">Riwayat Payout Seller</div>' + hHtml + '</div>';
                }

                body.innerHTML = html;
            }).catch(function () {
                body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">Gagal memuat detail payout.</div>';
            });
        }

        function openAuditLogDetail(logId) {
            var body = document.getElementById("utAdminAuditLogModalBody");
            if (!body) return;

            function badge(text, tone) {
                return '<span class="ut-admin-badge ut-admin-badge-' + escapeHtml(tone || "gray") + '">' +
                    '<span class="ut-admin-badge-dot"></span>' + escapeHtml(text || "-") + '</span>';
            }

            function row(label, value) {
                return '<div class="ut-admin-detail-row"><span class="ut-admin-detail-label">' +
                    escapeHtml(label || "-") + '</span><span class="ut-admin-detail-value">' +
                    escapeHtml(value == null || value === "" ? "-" : value) + '</span></div>';
            }

            function section(title, content) {
                if (!content) return "";
                return '<div class="ut-admin-modal-section"><div class="ut-admin-modal-section-title">' +
                    escapeHtml(title || "-") + '</div>' + content + '</div>';
            }

            function renderDetail(d) {
                var target = d.target || {};
                var html = '';
                html += '<div class="ut-admin-cs-detail-head">';
                html += '<div><div class="ut-admin-product-detail-title">' + escapeHtml(d.action_label || "-") + '</div>';
                html += '<div class="ut-admin-product-detail-meta">' + escapeHtml(d.action || "-") + '</div></div>';
                html += '<div class="ut-admin-product-detail-badges">' + badge(d.severity_label || "-", d.badge_class || "gray") + '</div>';
                html += '</div>';

                var infoHtml = "";
                infoHtml += row("Waktu", d.date || "-");
                infoHtml += row("Aktor", (d.actor || "-") + (d.actor_email ? " (" + d.actor_email + ")" : ""));
                infoHtml += row("Record", target.name || "-");
                infoHtml += row("Model", target.model || "-");
                infoHtml += row("Record ID", target.id || "-");
                infoHtml += row("Record Masih Ada", target.exists ? "Ya" : "Tidak / tidak bisa dicek");
                html += section("Informasi Log", infoHtml);

                html += section("Deskripsi",
                    '<p class="ut-admin-product-detail-description">' + escapeHtml(d.description || "-") + '</p>');

                if (d.payload) {
                    html += section("Payload",
                        '<pre class="ut-admin-audit-payload">' + escapeHtml(d.payload) + '</pre>');
                }

                if (target.admin_url) {
                    html += section("Halaman Admin Terkait",
                        '<a href="' + escapeHtml(target.admin_url) + '" class="ut-admin-btn ut-admin-btn-secondary ut-admin-btn-sm">' +
                        'Buka di Dashboard Admin</a>');
                }

                body.innerHTML = html;
            }

            body.innerHTML = '<div style="text-align:center;color:var(--utad-muted);padding:40px">Memuat...</div>';
            openModal("utAdminAuditLogModal");
            callJsonRpc("/unitrade/admin/api/audit-logs/detail", {
                log_id: logId,
            }).then(function (res) {
                var d = res.result || {};
                if (d.ok) {
                    renderDetail(d);
                } else {
                    body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                        escapeHtml(d.error || "Log aktivitas tidak ditemukan.") + '</div>';
                }
            }).catch(function () {
                body.innerHTML = '<div style="text-align:center;color:var(--utad-red);padding:40px">' +
                    'Gagal memuat detail log.</div>';
            });
        }

        // ---- Sidebar mobile toggle ----------------------------------------
        var hamburger = root.querySelector("#utAdminHamburger");
        var sidebar = root.querySelector(".ut-admin-sidebar");
        if (hamburger && sidebar) {
            hamburger.addEventListener("click", function () {
                sidebar.classList.toggle("ut-admin-open");
            });
        }

        // ---- Profile dropdown --------------------------------------------
        var profileBtn = root.querySelector("#utAdminProfileBtn");
        if (profileBtn) {
            profileBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                profileBtn.classList.toggle("ut-admin-open");
            });
            document.addEventListener("click", function (e) {
                if (!profileBtn.contains(e.target)) {
                    profileBtn.classList.remove("ut-admin-open");
                }
            });
            profileBtn.addEventListener("keydown", function (e) {
                if (e.key === "Escape") profileBtn.classList.remove("ut-admin-open");
            });
        }

        // ---- Notification button + dropdown -------------------------------
        var notifWrap = root.querySelector("#utAdminNotifWrap");
        var notifBtn = root.querySelector("#utAdminNotifBtn");
        var notifList = root.querySelector("#utAdminNotifList");
        var notifBadge = root.querySelector("#utAdminNotifBadge");
        var notifClear = root.querySelector("#utAdminNotifClear");

        function markRead(id) {
            if (!id || String(id) === "0") {
                return Promise.resolve({ result: { ok: true } });
            }
            return callJsonRpc("/unitrade/admin/api/notifications/read", {
                notification_id: id,
            });
        }

        function renderNotif(items) {
            if (!notifList) return;
            if (!items.length) {
                notifList.innerHTML = '<div style="padding:24px;text-align:center;color:var(--utad-muted);font-size:12px">' +
                    'Tidak ada notifikasi.</div>';
                if (notifBadge) notifBadge.style.display = "none";
                return;
            }
            var unreadCount = 0;
            var html = items.map(function (it) {
                var unread = it.id && !it.is_read;
                if (unread) unreadCount++;
                var levelClass = it.level === "urgent" ? "ut-admin-urgent"
                              : it.level === "warning" ? "ut-admin-warning"
                              : "ut-admin-info";
                return '' +
                    '<a class="ut-admin-notif-item ' + (unread ? 'ut-admin-unread' : '') + '" ' +
                       'href="' + escapeHtml(it.target_url || '#') + '" ' +
                       'data-notif-id="' + escapeHtml(it.id) + '">' +
                        '<div class="ut-admin-notif-dot ' + levelClass + '"></div>' +
                        '<div style="flex:1;min-width:0">' +
                            '<div class="ut-admin-notif-text">' + escapeHtml(it.title) + '</div>' +
                            (it.message
                                ? '<div class="ut-admin-notif-msg">' + escapeHtml(it.message) + '</div>'
                                : '') +
                            (it.time_label
                                ? '<div class="ut-admin-notif-time">' + escapeHtml(it.time_label) + '</div>'
                                : '') +
                        '</div>' +
                    '</a>';
            }).join("");
            notifList.innerHTML = html;
            if (notifBadge) {
                if (unreadCount > 0) {
                    notifBadge.style.display = "flex";
                    notifBadge.textContent = unreadCount;
                } else {
                    notifBadge.style.display = "none";
                }
            }
        }

        function loadNotifications() {
            callJsonRpc("/unitrade/admin/api/notifications", {}).then(function (res) {
                var data = res.result || { items: [] };
                renderNotif(data.items || []);
            });
        }

        if (notifBtn && notifWrap) {
            notifBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                var willOpen = !notifWrap.classList.contains("ut-admin-open");
                notifWrap.classList.toggle("ut-admin-open");
                if (profileBtn) profileBtn.classList.remove("ut-admin-open");
                if (willOpen) loadNotifications();
            });

            document.addEventListener("click", function (e) {
                if (!notifWrap.contains(e.target)) {
                    notifWrap.classList.remove("ut-admin-open");
                }
            });

            // Click on notification item → mark as read
            notifList.addEventListener("click", function (e) {
                var item = e.target.closest("[data-notif-id]");
                if (!item) return;
                e.preventDefault();
                var href = item.getAttribute("href") || "#";
                var hadHref = href && href !== "#" && href !== "";
                markRead(item.dataset.notifId).finally(function () {
                    if (hadHref) {
                        window.location.href = href;
                    } else {
                        // Tidak ada halaman tujuan: kasih feedback supaya user tidak bingung
                        item.classList.remove("ut-admin-unread");
                        showToast("Notifikasi ditandai sebagai sudah dibaca.", "success");
                        // Update badge count
                        var unreadLeft = notifList.querySelectorAll(".ut-admin-unread").length;
                        if (notifBadge) {
                            if (unreadLeft > 0) {
                                notifBadge.textContent = unreadLeft;
                            } else {
                                notifBadge.style.display = "none";
                            }
                        }
                    }
                });
            });

            // "Tandai semua dibaca"
            if (notifClear) {
                notifClear.addEventListener("click", function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    callJsonRpc("/unitrade/admin/api/notifications/read_all", {}).then(function () {
                        notifList.querySelectorAll("[data-notif-id]").forEach(function (el) {
                            el.classList.remove("ut-admin-unread");
                        });
                        if (notifBadge) notifBadge.style.display = "none";
                    });
                });
            }

            // Initial load (so badge count is correct without opening dropdown)
            loadNotifications();
            // Refresh every 60 seconds
            setInterval(loadNotifications, 60000);
        }

        // ---- Action buttons on users table -------------------------------
        function refresh() { window.location.reload(); }
        function refreshWithFeedback(message, tone) {
            showToast(message || "Aksi berhasil. Memuat ulang data...", tone || "success");
            root.classList.add("ut-admin-refreshing");
            window.setTimeout(refresh, 900);
        }
        function setButtonLoading(button, label) {
            if (!button) return function () {};
            var originalHtml = button.innerHTML;
            button.disabled = true;
            button.setAttribute("aria-busy", "true");
            button.classList.add("ut-admin-btn-loading");
            button.textContent = label || "Memproses...";
            return function () {
                button.disabled = false;
                button.removeAttribute("aria-busy");
                button.classList.remove("ut-admin-btn-loading");
                button.innerHTML = originalHtml;
            };
        }

        function collectNamedValues(form) {
            var values = {};
            if (!form) return values;
            form.querySelectorAll("[name]").forEach(function (el) {
                values[el.name] = el.value;
            });
            return values;
        }

        var voucherDiscountType = root.querySelector("#utAdminVoucherDiscountType");
        var voucherFixedBox = root.querySelector("#utAdminVoucherFixedBox");
        var voucherPercentBox = root.querySelector("#utAdminVoucherPercentBox");
        function syncVoucherDiscountFields() {
            if (!voucherDiscountType || !voucherFixedBox || !voucherPercentBox) return;
            var isPercent = voucherDiscountType.value === "percent";
            voucherFixedBox.style.display = isPercent ? "none" : "";
            voucherPercentBox.style.display = isPercent ? "" : "none";
        }
        function setNamedValue(form, name, value) {
            if (!form) return;
            var field = form.querySelector('[name="' + name + '"]');
            if (field) field.value = value == null ? "" : value;
        }
        function setElementValue(id, value) {
            var field = document.getElementById(id);
            if (field) field.value = value == null ? "" : value;
        }
        function openVoucherModal(button) {
            var voucherForm = document.getElementById("utAdminVoucherForm");
            var title = document.getElementById("utAdminVoucherModalTitle");
            var submit = document.getElementById("utAdminVoucherSubmit");
            if (voucherForm) voucherForm.reset();
            if (button.dataset.mode === "edit") {
                setNamedValue(voucherForm, "voucher_id", button.dataset.voucherId);
                setNamedValue(voucherForm, "name", button.dataset.name);
                setNamedValue(voucherForm, "code", button.dataset.code);
                setNamedValue(voucherForm, "discount_type", button.dataset.discountType || "fixed");
                setNamedValue(voucherForm, "discount_amount", button.dataset.discountAmount);
                setNamedValue(voucherForm, "discount_percent", button.dataset.discountPercent);
                setNamedValue(voucherForm, "min_order_amount", button.dataset.minOrderAmount);
                setNamedValue(voucherForm, "date_start", button.dataset.dateStart);
                setNamedValue(voucherForm, "date_end", button.dataset.dateEnd);
                setNamedValue(voucherForm, "usage_limit", button.dataset.usageLimit);
                setNamedValue(voucherForm, "usage_limit_per_user", button.dataset.usageLimitPerUser);
                setNamedValue(voucherForm, "active", button.dataset.active === "true" ? "true" : "false");
                if (title) title.textContent = "Edit Voucher";
                if (submit) {
                    submit.textContent = "Simpan Perubahan";
                    submit.dataset.action = "save-voucher";
                }
            } else {
                setNamedValue(voucherForm, "voucher_id", "");
                if (title) title.textContent = "Buat Voucher";
                if (submit) {
                    submit.textContent = "Simpan Voucher";
                    submit.dataset.action = "save-voucher";
                }
            }
            syncVoucherDiscountFields();
            openModal("utAdminVoucherModal");
        }
        function openSponsorshipModal(button) {
            var sponsorshipForm = document.getElementById("utAdminSponsorshipForm");
            var submit = document.getElementById("utAdminSponsorshipSubmit");
            var sponsorshipId = button.dataset.sponsorshipId || "";
            if (!sponsorshipForm) return;

            sponsorshipForm.reset();
            sponsorshipForm.dataset.sponsorshipRow = sponsorshipId;
            setNamedValue(sponsorshipForm, "sponsorship_id", sponsorshipId);
            setNamedValue(sponsorshipForm, "sponsorship_status", button.dataset.status || "new");
            setNamedValue(sponsorshipForm, "sponsorship_note", button.dataset.note || "");

            setElementValue("utAdminSponsorshipName", button.dataset.name || "-");
            setElementValue("utAdminSponsorshipContact", button.dataset.contactName || "-");
            setElementValue("utAdminSponsorshipEmail", button.dataset.email || "-");
            setElementValue("utAdminSponsorshipPhone", button.dataset.phone || "-");
            setElementValue("utAdminSponsorshipBudget", button.dataset.budgetNote || "-");
            setElementValue("utAdminSponsorshipCreated", button.dataset.created || "-");
            setElementValue("utAdminSponsorshipGoal", button.dataset.campaignGoal || "-");

            if (submit) submit.dataset.sponsorshipId = sponsorshipId;
            openModal("utAdminSponsorshipModal");
        }
        if (voucherDiscountType) {
            voucherDiscountType.addEventListener("change", syncVoucherDiscountFields);
            syncVoucherDiscountFields();
        }

        root.addEventListener("click", async function (e) {
            var btn = e.target.closest("[data-action]");
            if (btn) {
                var action = btn.dataset.action;
                var userId = btn.dataset.userId;
                var sellerId = btn.dataset.sellerId;
                var verificationId = btn.dataset.verificationId;
                var orderId = btn.dataset.orderId;
                var notificationId = btn.dataset.notificationId;
                var voucherId = btn.dataset.voucherId;
                var ticketId = btn.dataset.ticketId;
                var sponsorshipId = btn.dataset.sponsorshipId;
                var productId = btn.dataset.productId;
                var reviewId = btn.dataset.reviewId;
                var payoutId = btn.dataset.payoutId;
                var announcementId = btn.dataset.announcementId;
                var caseType = btn.dataset.caseType;
                var caseId = btn.dataset.caseId;
                var logId = btn.dataset.logId;
                var reportType = btn.dataset.reportType;
                var reportId = btn.dataset.reportId;

                if (action === "block-user") {
                    var reason = await promptAdmin("Alasan blokir user ini?", {
                        title: "Blokir User",
                        multiline: true,
                        placeholder: "Tuliskan alasan singkat untuk catatan admin.",
                    });
                    if (!reason || !reason.trim()) return;
                    callJsonRpc("/unitrade/admin/api/users/block", { user_id: userId, reason: reason })
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast("Gagal memblokir user.", "error");
                        });
                } else if (action === "unblock-user") {
                    if (!await confirmAdmin("Aktifkan kembali user ini?", { title: "Aktifkan User" })) return;
                    callJsonRpc("/unitrade/admin/api/users/unblock", { user_id: userId })
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast("Gagal mengaktifkan user.", "error");
                        });
                } else if (action === "open-admin-modal") {
                    var adminForm = document.getElementById("utAdminCreateAdminForm");
                    if (adminForm) adminForm.reset();
                    openModal("utAdminCreateAdminModal");
                } else if (action === "create-admin") {
                    var createAdminForm = document.getElementById("utAdminCreateAdminForm");
                    var adminValues = collectNamedValues(createAdminForm);
                    if (!adminValues.name || !adminValues.email) {
                        showToast("Nama dan email admin wajib diisi.", "warning");
                        return;
                    }
                    var originalAdminLabel = btn.textContent;
                    btn.disabled = true;
                    btn.textContent = "Menyimpan...";
                    callJsonRpc("/unitrade/admin/api/admins/create", { values: adminValues })
                        .then(function (res) {
                            btn.disabled = false;
                            if (res.result && res.result.ok) {
                                showToast(res.result.message || "Admin berhasil disimpan.", "success");
                                refresh();
                            } else {
                                btn.textContent = originalAdminLabel;
                                showToast((res.result && res.result.error) || "Gagal menambahkan admin.", "error");
                            }
                        })
                        .catch(function () {
                            btn.disabled = false;
                            btn.textContent = originalAdminLabel;
                            showToast("Gagal menambahkan admin.", "error");
                        });
                } else if (action === "approve-seller") {
                    if (!await confirmAdmin("Approve verifikasi KTM seller ini?", { title: "Approve Seller" })) return;
                    var approveUrl = verificationId
                        ? "/unitrade/admin/api/verifications/approve"
                        : "/unitrade/admin/api/sellers/approve";
                    var approvePayload = verificationId
                        ? { verification_id: verificationId }
                        : { seller_id: sellerId };
                    var resetApproveButton = setButtonLoading(btn, "Approve...");
                    callJsonRpc(approveUrl, approvePayload)
                        .then(async function (res) {
                            if (res.result && res.result.ok) {
                                refreshWithFeedback("KTM berhasil di-approve. Data admin sedang diperbarui...", "success");
                            }
                            else if (res.result && res.result.error_code === "nim_required" && verificationId) {
                                resetApproveButton();
                                var manualNim = await promptAdmin(res.result.error, {
                                    title: "Lengkapi NIM",
                                    placeholder: "Contoh: 2411501058",
                                });
                                if (!manualNim || !manualNim.trim()) return;
                                resetApproveButton = setButtonLoading(btn, "Approve...");
                                callJsonRpc(approveUrl, {
                                    verification_id: verificationId,
                                    nim: manualNim.trim()
                                }).then(function (retryRes) {
                                    if (retryRes.result && retryRes.result.ok) {
                                        refreshWithFeedback("KTM berhasil di-approve. Data admin sedang diperbarui...", "success");
                                    } else {
                                        resetApproveButton();
                                        showToast((retryRes.result && retryRes.result.error) || "Gagal approve seller.", "error");
                                    }
                                }).catch(function () {
                                    resetApproveButton();
                                    showToast("Gagal approve seller. Coba ulangi beberapa saat lagi.", "error");
                                });
                            } else {
                                resetApproveButton();
                                showToast((res.result && res.result.error) || "Gagal approve seller.", "error");
                            }
                        })
                        .catch(function () {
                            resetApproveButton();
                            showToast("Gagal approve seller. Coba ulangi beberapa saat lagi.", "error");
                        });
                } else if (action === "reject-seller") {
                    var rreason = await promptAdmin("Alasan penolakan KTM?", {
                        title: "Tolak KTM",
                        multiline: true,
                        placeholder: "Contoh: Foto KTM tidak jelas.",
                    });
                    if (!rreason || !rreason.trim()) return;
                    var rejectUrl = verificationId
                        ? "/unitrade/admin/api/verifications/reject"
                        : "/unitrade/admin/api/sellers/reject";
                    var rejectPayload = verificationId
                        ? { verification_id: verificationId, reason: rreason }
                        : { seller_id: sellerId, reason: rreason };
                    var resetRejectButton = setButtonLoading(btn, "Menolak...");
                    callJsonRpc(rejectUrl, rejectPayload)
                        .then(function (res) {
                            if (res.result && res.result.ok) {
                                refreshWithFeedback("KTM berhasil ditolak. Data admin sedang diperbarui...", "success");
                            } else {
                                resetRejectButton();
                                showToast((res.result && res.result.error) || "Gagal menolak seller.", "error");
                            }
                        })
                        .catch(function () {
                            resetRejectButton();
                            showToast("Gagal menolak seller. Coba ulangi beberapa saat lagi.", "error");
                        });
                } else if (action === "reset-seller") {
                    if (!await confirmAdmin("Reset verifikasi seller ke draft?", { title: "Reset Seller" })) return;
                    callJsonRpc("/unitrade/admin/api/sellers/reset", { seller_id: sellerId })
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast("Gagal reset seller.", "error");
                        });
                } else if (action === "revoke-seller") {
                    var revokeReason = await promptAdmin("Alasan melepas status seller? Seller akan kembali jadi user biasa dan harus mendaftar ulang.", {
                        title: "Lepas Status Seller",
                        multiline: true,
                        placeholder: "Contoh: Terbukti menyalahgunakan KTM orang lain.",
                    });
                    if (!revokeReason || !revokeReason.trim()) return;
                    var resetRevokeButton = setButtonLoading(btn, "Melepas...");
                    callJsonRpc("/unitrade/admin/api/sellers/revoke", { seller_id: sellerId, reason: revokeReason })
                        .then(function (res) {
                            if (res.result && res.result.ok) {
                                refreshWithFeedback("Status seller berhasil dilepas. Data admin sedang diperbarui...", "success");
                            } else {
                                resetRevokeButton();
                                showToast((res.result && res.result.error) || "Gagal melepas status seller.", "error");
                            }
                        })
                        .catch(function () {
                            resetRevokeButton();
                            showToast("Gagal melepas status seller. Coba ulangi beberapa saat lagi.", "error");
                        });
                } else if (action === "user-detail") {
                    openUserDetail(userId);
                } else if (action === "save-user-note") {
                    var noteEl = document.getElementById("utAdminUserNote");
                    var nuserId = btn.dataset.userId;
                    callJsonRpc("/unitrade/admin/api/users/note",
                                { user_id: nuserId, note: noteEl ? noteEl.value : "" })
                        .then(function (res) {
                            if (res.result && res.result.ok) {
                                btn.textContent = "Tersimpan ✓";
                                setTimeout(function () { btn.textContent = "Simpan Catatan"; }, 1500);
                            } else {
                                showToast("Gagal menyimpan catatan.", "error");
                            }
                        });
                } else if (action === "resend-otp") {
                    callJsonRpc("/unitrade/admin/api/users/resend_otp", { user_id: btn.dataset.userId })
                        .then(function (res) {
                            if (res.result && res.result.ok) showToast("OTP terkirim.", "success");
                            else showToast("Gagal kirim OTP.", "error");
                        });
                } else if (action === "order-detail") {
                    openOrderDetail(orderId);
                } else if (action === "flag-order") {
                    var freason = await promptAdmin("Alasan tandai bermasalah?", {
                        title: "Tandai Transaksi",
                        multiline: true,
                    });
                    if (!freason || !freason.trim()) return;
                    callJsonRpc("/unitrade/admin/api/orders/flag", { order_id: orderId, reason: freason })
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast("Gagal menandai.", "error");
                        });
                } else if (action === "unflag-order") {
                    if (!await confirmAdmin("Hapus tanda bermasalah?", { title: "Pulihkan Transaksi" })) return;
                    callJsonRpc("/unitrade/admin/api/orders/unflag", { order_id: orderId })
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast("Gagal menghapus tanda.", "error");
                        });
                } else if (action === "mark-notification-read") {
                    callJsonRpc("/unitrade/admin/api/notifications/read", { notification_id: notificationId })
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast("Gagal menandai notifikasi.", "error");
                        });
                } else if (action === "open-notification-target") {
                    // Klik "Buka target" → mark read otomatis lalu navigate.
                    e.preventDefault();
                    var openHref = btn.getAttribute("data-target-url") || btn.getAttribute("href") || "";
                    var openPromise = notificationId
                        ? callJsonRpc("/unitrade/admin/api/notifications/read", { notification_id: notificationId })
                        : Promise.resolve();
                    openPromise.finally(function () {
                        if (openHref) {
                            window.location.href = openHref;
                        }
                    });
                } else if (action === "settings-cancel") {
                    // Tombol "Batal" pada halaman Settings → reload form ke nilai tersimpan
                    window.location.reload();
                } else if (action === "mark-all-notifications") {
                    callJsonRpc("/unitrade/admin/api/notifications/read_all", {})
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast("Gagal menandai semua notifikasi.", "error");
                        });
                } else if (action === "open-voucher-modal") {
                    openVoucherModal(btn);
                } else if (action === "create-voucher" || action === "save-voucher") {
                    var form = document.getElementById("utAdminVoucherForm");
                    var originalLabel = btn.textContent;
                    var voucherValues = collectNamedValues(form);
                    var isEditVoucher = !!voucherValues.voucher_id;
                    btn.disabled = true;
                    btn.textContent = "Menyimpan...";
                    callJsonRpc(
                        isEditVoucher ? "/unitrade/admin/api/vouchers/update" : "/unitrade/admin/api/vouchers/create",
                        { voucher_id: voucherValues.voucher_id, values: voucherValues }
                    )
                        .then(function (res) {
                            btn.disabled = false;
                            if (res.result && res.result.ok) {
                                refresh();
                            } else {
                                btn.textContent = originalLabel;
                                showToast((res.result && res.result.error) || "Gagal menyimpan voucher.", "error");
                            }
                        })
                        .catch(function () {
                            btn.disabled = false;
                            btn.textContent = originalLabel;
                            showToast("Gagal menyimpan voucher.", "error");
                        });
                } else if (action === "toggle-voucher") {
                    var shouldActivate = btn.dataset.active === "true";
                    if (!await confirmAdmin((shouldActivate ? "Aktifkan" : "Nonaktifkan") + " voucher ini?", {
                        title: shouldActivate ? "Aktifkan Voucher" : "Nonaktifkan Voucher",
                    })) return;
                    callJsonRpc("/unitrade/admin/api/vouchers/toggle", {
                        voucher_id: voucherId,
                        active: shouldActivate,
                    }).then(function (res) {
                        if (res.result && res.result.ok) refresh();
                        else showToast((res.result && res.result.error) || "Gagal memperbarui voucher.", "error");
                    });
                } else if (action === "voucher-detail") {
                    openVoucherDetail(voucherId);
                } else if (action === "product-detail") {
                    openProductDetail(productId);
                } else if (action === "cs-detail") {
                    openCustomerServiceDetail(caseType, caseId);
                } else if (action === "report-detail") {
                    openReportDetail(reportType, reportId);
                } else if (action === "report-set-status") {
                    var rStatus = btn.dataset.status;
                    var rType = reportType;
                    var rId = reportId;
                    var rNote = "";
                    if (rStatus === "rejected" || rStatus === "done") {
                        rNote = await promptAdmin(
                            rStatus === "rejected" ? "Alasan menolak laporan ini?" : "Catatan penyelesaian (opsional):",
                            {
                                title: rStatus === "rejected" ? "Tolak Laporan" : "Selesaikan Laporan",
                                multiline: true,
                            }
                        );
                        if (rStatus === "rejected" && (!rNote || !rNote.trim())) return;
                        rNote = (rNote || "").trim();
                    }
                    callJsonRpc("/unitrade/admin/api/report-list/set-status", {
                        report_type: rType,
                        report_id: rId,
                        status: rStatus,
                        note: rNote,
                    }).then(function (res) {
                        if (res.result && res.result.ok) {
                            showToast("Status laporan diperbarui.", "success");
                            openReportDetail(rType, rId);
                        } else {
                            showToast((res.result && res.result.error) || "Gagal memperbarui laporan.", "error");
                        }
                    });
                } else if (action === "audit-log-detail") {
                    openAuditLogDetail(logId);
                } else if (action === "product-action") {
                    var productActionName = btn.dataset.productAction;
                    var productPayload = {
                        product_id: productId,
                        action: productActionName,
                        publish_after: btn.dataset.publishAfter !== "false",
                    };
                    if (productActionName === "publish") {
                        if (!await confirmAdmin("Publish produk ini ke marketplace?", { title: "Publish Produk" })) return;
                    } else if (productActionName === "unpublish") {
                        if (!await confirmAdmin("Sembunyikan produk ini dari marketplace?", { title: "Unpublish Produk" })) return;
                    } else if (productActionName === "waive") {
                        var waiveReason = await promptAdmin("Alasan waive fee listing produk:", {
                            title: "Waive Fee Produk",
                            multiline: true,
                            placeholder: "Contoh: kompensasi admin setelah validasi manual.",
                        });
                        if (!waiveReason || !waiveReason.trim()) return;
                        productPayload.reason = waiveReason.trim();
                    } else if (productActionName === "reject") {
                        var rejectReason = await promptAdmin("Alasan produk ditolak:", {
                            title: "Tolak Listing Produk",
                            multiline: true,
                            placeholder: "Contoh: Foto produk tidak jelas atau deskripsi tidak sesuai.",
                        });
                        if (!rejectReason || !rejectReason.trim()) return;
                        productPayload.reason = rejectReason.trim();
                    } else {
                        return;
                    }
                    var originalProductLabel = btn.textContent;
                    btn.disabled = true;
                    btn.textContent = "Memproses...";
                    callJsonRpc("/unitrade/admin/api/products/action", productPayload)
                        .then(function (res) {
                            btn.disabled = false;
                            if (res.result && res.result.ok) {
                                showToast("Aksi produk berhasil diproses.", "success");
                                refresh();
                            } else {
                                btn.textContent = originalProductLabel;
                                showToast((res.result && res.result.error) || "Gagal memproses produk.", "error");
                            }
                        })
                        .catch(function () {
                            btn.disabled = false;
                            btn.textContent = originalProductLabel;
                            showToast("Gagal memproses produk.", "error");
                        });
                } else if (action === "ticket-reply") {
                    // Cek dulu apakah tiket ini punya sesi live chat aktif.
                    // Jika ada -> arahkan admin ke halaman Live Chat (bukan balas tiket).
                    var lcRedirected = false;
                    try {
                        var lcRes = await callJsonRpc("/unitrade/admin/api/live-chat/session-for-ticket", {
                            ticket_id: ticketId,
                        });
                        var lcSessionId = lcRes && lcRes.result && lcRes.result.session_id;
                        if (lcSessionId) {
                            window.location.href = "/unitrade/admin/live-chat?session_id=" + encodeURIComponent(lcSessionId);
                            lcRedirected = true;
                        }
                    } catch (err) {
                        // Abaikan, fallback ke balas tiket biasa di bawah.
                    }
                    if (lcRedirected) return;

                    var replyBody = await promptAdmin("Balasan untuk user:", {
                        title: "Balas Tiket Bantuan",
                        multiline: true,
                        placeholder: "Tulis jawaban atau instruksi lanjutan untuk user.",
                    });
                    if (!replyBody || !replyBody.trim()) return;
                    callJsonRpc("/unitrade/admin/api/customer-tickets/reply", {
                        ticket_id: ticketId,
                        body: replyBody.trim(),
                    }).then(function (res) {
                        if (res.result && res.result.ok) {
                            showToast("Balasan terkirim.", "success");
                            openCustomerServiceDetail("ticket", ticketId);
                        } else {
                            showToast((res.result && res.result.error) || "Gagal mengirim balasan.", "error");
                        }
                    });
                } else if (action === "ticket-status") {
                    var ticketStatus = btn.dataset.status;
                    // "Di Proses" -> jika tiket punya sesi live chat, ambil alih
                    // sesi (admin_handling + notif user) lalu arahkan ke live chat.
                    if (ticketStatus === "in_progress") {
                        var startSessionId = 0;
                        try {
                            var sres = await callJsonRpc("/unitrade/admin/api/live-chat/session-for-ticket", {
                                ticket_id: ticketId,
                            });
                            startSessionId = (sres && sres.result && sres.result.session_id) || 0;
                        } catch (err) {
                            startSessionId = 0;
                        }
                        if (startSessionId) {
                            var startRes = await callJsonRpc("/unitrade/admin/api/cs/start", {
                                session_id: startSessionId,
                            });
                            if (startRes && startRes.result && startRes.result.success) {
                                window.location.href = "/unitrade/admin/live-chat?session_id=" +
                                    encodeURIComponent(startSessionId);
                                return;
                            }
                            showToast(
                                (startRes && startRes.result && startRes.result.message) ||
                                "Gagal membuka live chat.",
                                "error"
                            );
                            return;
                        }
                        // tidak ada sesi live chat -> lanjut update status tiket biasa
                    }
                    var ticketNote = "";
                    if (ticketStatus === "done") {
                        ticketNote = await promptAdmin("Catatan penyelesaian untuk user:", {
                            title: "Selesaikan Tiket",
                            multiline: true,
                            placeholder: "Contoh: Refund sudah diarahkan ke halaman pengembalian resmi dan akan ditinjau admin.",
                        });
                        if (!ticketNote || !ticketNote.trim()) return;
                        ticketNote = ticketNote.trim();
                    }
                    callJsonRpc("/unitrade/admin/api/customer-tickets/status", {
                        ticket_id: ticketId,
                        status: ticketStatus,
                        note: ticketNote,
                    }).then(function (res) {
                        if (res.result && res.result.ok) {
                            var csModal = document.getElementById("utAdminCsCaseModal");
                            if (csModal && csModal.classList.contains("ut-admin-show")) {
                                openCustomerServiceDetail("ticket", ticketId);
                            } else {
                                refresh();
                            }
                        } else {
                            showToast((res.result && res.result.error) || "Gagal memperbarui tiket.", "error");
                        }
                    });
                } else if (action === "open-sponsorship-modal") {
                    openSponsorshipModal(btn);
                } else if (action === "sponsorship-update") {
                    var sponsorshipForm = btn.closest("[data-sponsorship-row]");
                    var sponsorshipRequestId = sponsorshipId || (
                        sponsorshipForm && sponsorshipForm.querySelector('[name="sponsorship_id"]')
                            ? sponsorshipForm.querySelector('[name="sponsorship_id"]').value
                            : ""
                    );
                    var sponsorshipStatus = sponsorshipForm
                        ? sponsorshipForm.querySelector('[name="sponsorship_status"]').value
                        : "";
                    var sponsorshipNote = sponsorshipForm
                        ? sponsorshipForm.querySelector('[name="sponsorship_note"]').value
                        : "";
                    var originalSponsorshipLabel = btn.textContent;
                    btn.disabled = true;
                    btn.textContent = "Menyimpan...";
                    callJsonRpc("/unitrade/admin/api/sponsorships/update", {
                        request_id: sponsorshipRequestId,
                        status: sponsorshipStatus,
                        note: sponsorshipNote,
                    }).then(function (res) {
                        btn.disabled = false;
                        if (res.result && res.result.ok) refresh();
                        else {
                            btn.textContent = originalSponsorshipLabel;
                            showToast((res.result && res.result.error) || "Gagal memperbarui sponsorship.", "error");
                        }
                    }).catch(function () {
                        btn.disabled = false;
                        btn.textContent = originalSponsorshipLabel;
                        showToast("Gagal memperbarui sponsorship.", "error");
                    });
                } else if (action === "review-visibility") {
                    var visible = btn.dataset.visible === "true" || btn.dataset.visible === "True";
                    var message = visible ? "Tampilkan ulasan ini lagi?" : "Sembunyikan ulasan ini dari storefront?";
                    if (!await confirmAdmin(message, { title: visible ? "Tampilkan Ulasan" : "Sembunyikan Ulasan" })) return;
                    callJsonRpc("/unitrade/admin/api/reviews/visibility", {
                        review_id: reviewId,
                        visible: visible,
                    }).then(function (res) {
                        if (res.result && res.result.ok) refresh();
                        else showToast((res.result && res.result.error) || "Gagal memperbarui ulasan.", "error");
                    });
                } else if (action === "review-detail") {
                    openReviewDetail(reviewId);
                } else if (action === "payout-action") {
                    var payoutAction = btn.dataset.payoutAction;
                    var payload = {
                        payout_id: payoutId,
                        action: payoutAction,
                    };
                    if (payoutAction === "ready" && !await confirmAdmin("Tandai payout ini siap dibayar?", { title: "Payout Siap" })) return;
                    if (payoutAction === "recompute" && !await confirmAdmin("Refresh ledger payout dari escrow eligible terbaru?", { title: "Refresh Payout" })) return;
                    if (payoutAction === "paid") {
                        var paymentReference = await promptAdmin("Isi payment reference / nomor bukti transfer:", {
                            title: "Tandai Payout Paid",
                            placeholder: "Contoh: TRF-2026-001",
                        });
                        if (!paymentReference || !paymentReference.trim()) return;
                        payload.payment_reference = paymentReference.trim();
                    }
                    if (payoutAction === "cancel") {
                        var cancelReason = await promptAdmin("Alasan pembatalan payout:", {
                            title: "Batalkan Payout",
                            multiline: true,
                        });
                        if (!cancelReason || !cancelReason.trim()) return;
                        payload.cancel_reason = cancelReason.trim();
                    }
                    callJsonRpc("/unitrade/admin/api/payouts/action", payload)
                        .then(function (res) {
                            if (res.result && res.result.ok) refresh();
                            else showToast((res.result && res.result.error) || "Gagal menjalankan aksi payout.", "error");
                        });
                } else if (action === "payout-detail") {
                    openPayoutDetail(payoutId);
                } else if (action === "refund-action") {
                    var refundId = btn.dataset.refundId;
                    var refundAction = btn.dataset.refundAction;
                    var refundPayload = { dispute_id: refundId, action: refundAction };

                    if (refundAction === "start_review") {
                        if (!await confirmAdmin("Jadikan diri Anda penengah refund ini?", { title: "Jadi Penengah" })) return;
                    } else if (refundAction === "need_buyer_evidence") {
                        if (!await confirmAdmin("Minta bukti tambahan dari buyer?", { title: "Minta Bukti Buyer" })) return;
                    } else if (refundAction === "need_seller_response") {
                        if (!await confirmAdmin("Minta respons dari seller?", { title: "Minta Respons Seller" })) return;
                    } else if (refundAction === "approve") {
                        var approveNote = await promptAdmin("Catatan keputusan approve (min 10 karakter, wajib):", {
                            title: "Approve Refund",
                            multiline: true,
                            placeholder: "Alasan menyetujui refund berdasarkan bukti.",
                        });
                        if (!approveNote || approveNote.trim().length < 10) {
                            showToast("Catatan keputusan minimal 10 karakter.", "warning");
                            return;
                        }
                        refundPayload.note = approveNote.trim();
                    } else if (refundAction === "reject") {
                        var rejectNote = await promptAdmin("Catatan keputusan reject (min 10 karakter, wajib):", {
                            title: "Reject Refund",
                            multiline: true,
                            placeholder: "Alasan menolak refund berdasarkan bukti.",
                        });
                        if (!rejectNote || rejectNote.trim().length < 10) {
                            showToast("Catatan keputusan minimal 10 karakter.", "warning");
                            return;
                        }
                        refundPayload.note = rejectNote.trim();
                    } else if (refundAction === "cancel") {
                        var cancelRefundReason = await promptAdmin("Alasan membatalkan case refund:", {
                            title: "Batalkan Case",
                            multiline: true,
                        });
                        if (!cancelRefundReason || !cancelRefundReason.trim()) return;
                        refundPayload.note = cancelRefundReason.trim();
                    }
                    btn.disabled = true;
                    callJsonRpc("/unitrade/admin/api/refunds/action", refundPayload)
                        .then(function (res) {
                            btn.disabled = false;
                            if (res.result && res.result.ok) {
                                showToast(res.result.message || "Keputusan refund tersimpan.", "success");
                                refresh();
                            } else {
                                showToast((res.result && res.result.error) || "Gagal memproses refund.", "error");
                            }
                        })
                        .catch(function () {
                            btn.disabled = false;
                            showToast("Gagal memproses refund.", "error");
                        });
                } else if (action === "open-announcement-modal") {
                    var announcementForm = document.getElementById("utAdminAnnouncementForm");
                    if (announcementForm) announcementForm.reset();
                    openModal("utAdminAnnouncementModal");
                } else if (action === "announcement-detail") {
                    openAnnouncementDetail(announcementId, btn);
                } else if (action === "announcement-create") {
                    var annForm = document.getElementById("utAdminAnnouncementForm");
                    var annValues = collectNamedValues(annForm);
                    if (!annValues.title || !annValues.body) {
                        showToast("Judul dan isi pengumuman wajib diisi.", "warning");
                        return;
                    }
                    var originalAnnLabel = btn.textContent;
                    btn.disabled = true;
                    btn.textContent = "Menyimpan...";
                    callJsonRpc("/unitrade/admin/api/announcements/create", { values: annValues })
                        .then(function (res) {
                            btn.disabled = false;
                            if (res.result && res.result.ok) refresh();
                            else {
                                btn.textContent = originalAnnLabel;
                                showToast((res.result && res.result.error) || "Gagal membuat pengumuman.", "error");
                            }
                        })
                        .catch(function () {
                            btn.disabled = false;
                            btn.textContent = originalAnnLabel;
                            showToast("Gagal membuat pengumuman.", "error");
                        });
                } else if (action === "announcement-publish") {
                    if (!await confirmAdmin("Publish pengumuman ini ke semua user aktif?", { title: "Publish Pengumuman" })) return;
                    var originalPublishLabel = btn.textContent;
                    btn.disabled = true;
                    btn.textContent = "Memproses...";
                    callJsonRpc("/unitrade/admin/api/announcements/publish", {
                        announcement_id: announcementId,
                    }).then(function (res) {
                        btn.disabled = false;
                        if (res.result && res.result.ok) {
                            showToast(
                                "Pengumuman terkirim ke " + (res.result.visible || 0) + " user.",
                                "success"
                            );
                            window.setTimeout(refresh, 650);
                        } else {
                            btn.textContent = originalPublishLabel;
                            showToast((res.result && res.result.error) || "Gagal publish pengumuman.", "error");
                        }
                    }).catch(function () {
                        btn.disabled = false;
                        btn.textContent = originalPublishLabel;
                        showToast("Gagal publish pengumuman.", "error");
                    });
                } else if (action === "announcement-sync") {
                    if (!await confirmAdmin("Sinkronkan ulang notifikasi pengumuman ini?", { title: "Sinkron Notifikasi" })) return;
                    var originalSyncLabel = btn.textContent;
                    btn.disabled = true;
                    btn.textContent = "Sinkron...";
                    callJsonRpc("/unitrade/admin/api/announcements/sync", {
                        announcement_id: announcementId,
                    }).then(function (res) {
                        btn.disabled = false;
                        if (res.result && res.result.ok) {
                            showToast(
                                "Notifikasi tersedia untuk " + (res.result.visible || 0) + " user.",
                                "success"
                            );
                            window.setTimeout(refresh, 650);
                        } else {
                            btn.textContent = originalSyncLabel;
                            showToast((res.result && res.result.error) || "Gagal sinkron notifikasi.", "error");
                        }
                    }).catch(function () {
                        btn.disabled = false;
                        btn.textContent = originalSyncLabel;
                        showToast("Gagal sinkron notifikasi.", "error");
                    });
                }
                return;
            }

            // Modal close button / overlay click
            var closer = e.target.closest("[data-modal-close]");
            if (closer) {
                closeModal(closer.dataset.modalClose);
                return;
            }
            // Click on overlay background closes modal
            if (e.target.classList && e.target.classList.contains("ut-admin-modal-overlay")) {
                closeModal(e.target.id);
            }
        });

        // ---- Settings save ------------------------------------------------
        var FEE_DEFAULTS = {
            "unitrade.seller.listing_fee.enabled": "True",
            "unitrade.seller.listing_fee.threshold": "1000000",
            "unitrade.seller.listing_fee.low_amount": "2000",
            "unitrade.seller.listing_fee.high_amount": "5000",
            "unitrade.seller.listing_fee.validity_days": "30",
            "unitrade.seller.posting_admin_fee": "0",
        };
        var FEE_NUMERIC_RULES = {
            "unitrade.seller.listing_fee.threshold": { label: "Batas Harga Produk", min: 0 },
            "unitrade.seller.listing_fee.low_amount": { label: "Fee Harga di Bawah Batas", min: 0 },
            "unitrade.seller.listing_fee.high_amount": { label: "Fee Harga di Atas/Sama Batas", min: 0 },
            "unitrade.seller.listing_fee.validity_days": { label: "Masa Berlaku Listing", min: 1 },
            "unitrade.seller.posting_admin_fee": { label: "Admin Fee Tambahan", min: 0 },
            "unitrade.xendit.payment_expiry_minutes": { label: "Expired Pembayaran Xendit", min: 1 },
        };

        function setFormValue(form, name, value) {
            var field = form.querySelector('[name="' + name + '"]');
            if (field) field.value = value;
        }

        function collectSettingsValues(form) {
            var values = {};
            form.querySelectorAll("[name]").forEach(function (el) {
                values[el.name] = el.value;
            });
            return values;
        }

        function validateSettings(values) {
            var names = Object.keys(FEE_NUMERIC_RULES);
            for (var i = 0; i < names.length; i += 1) {
                var name = names[i];
                var rule = FEE_NUMERIC_RULES[name];
                var raw = values[name];
                var numberValue = Number(raw);
                if (raw === "" || !Number.isFinite(numberValue)) {
                    return rule.label + " harus berupa angka.";
                }
                if (numberValue < rule.min) {
                    if (rule.min === 1) {
                        return rule.label + " minimal 1 hari.";
                    }
                    return rule.label + " tidak boleh negatif.";
                }
            }
            return "";
        }

        function saveSettings(button, successLabel) {
            var form = document.getElementById("utAdminSettingsForm");
            if (!form) return;
            var values = collectSettingsValues(form);
            var validationError = validateSettings(values);
            if (validationError) {
                showToast(validationError, "warning");
                return;
            }
            var origLabel = button.textContent;
            button.textContent = "Menyimpan...";
            button.disabled = true;
            callJsonRpc("/unitrade/admin/api/settings/save", { values: values })
                .then(function (res) {
                    button.disabled = false;
                    if (res.result && res.result.ok) {
                        button.textContent = successLabel || "Tersimpan ✓";
                        setTimeout(function () { button.textContent = origLabel; }, 1800);
                    } else {
                        button.textContent = origLabel;
                        showToast((res.result && res.result.error) || "Gagal menyimpan pengaturan.", "error");
                    }
                })
                .catch(function () {
                    button.disabled = false;
                    button.textContent = origLabel;
                    showToast("Gagal menyimpan pengaturan.", "error");
                });
        }
        var saveBtnTop = root.querySelector("#utAdminSettingsSave");
        var saveBtnBottom = root.querySelector("#utAdminSettingsSaveBottom");
        var resetFeeBtn = root.querySelector("#utAdminFeeDefaults");
        if (saveBtnTop) saveBtnTop.addEventListener("click", function () { saveSettings(saveBtnTop); });
        if (saveBtnBottom) saveBtnBottom.addEventListener("click", function () { saveSettings(saveBtnBottom); });
        if (resetFeeBtn) {
            resetFeeBtn.addEventListener("click", function () {
                var form = document.getElementById("utAdminSettingsForm");
                if (!form) return;
                Object.keys(FEE_DEFAULTS).forEach(function (name) {
                    setFormValue(form, name, FEE_DEFAULTS[name]);
                });
                saveSettings(resetFeeBtn, "Default diterapkan");
            });
        }

        // ---- GMV chart (only on dashboard page) --------------------------
        var canvas = root.querySelector("#utAdminGmvChart");
        if (canvas && window.Chart) {
            try {
                var series = JSON.parse(canvas.dataset.series || "[]");
                var ctx = canvas.getContext("2d");
                var grad = ctx.createLinearGradient(0, 0, 0, 220);
                grad.addColorStop(0, "rgba(17,24,39,.18)");
                grad.addColorStop(1, "rgba(17,24,39,.01)");

                new window.Chart(ctx, {
                    type: "line",
                    data: {
                        labels: series.map(function (p) { return p.label; }),
                        datasets: [{
                            label: "GMV (Rp)",
                            data: series.map(function (p) { return p.value; }),
                            borderColor: "#111827",
                            borderWidth: 2.5,
                            backgroundColor: grad,
                            tension: 0.4,
                            fill: true,
                            pointBackgroundColor: "#111827",
                            pointRadius: 3,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function (ctx) {
                                        return "Rp " + Number(ctx.parsed.y || 0).toLocaleString("id-ID");
                                    },
                                },
                            },
                        },
                        scales: {
                            x: { grid: { display: false } },
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    callback: function (v) {
                                        return "Rp " + Number(v).toLocaleString("id-ID", { notation: "compact" });
                                    },
                                },
                            },
                        },
                    },
                });
            } catch (err) {
                console.warn("GMV chart render failed", err);
            }
        }

        // ================================================================
        // LIVE CHAT (admin <-> user) — reuse endpoint /api/cs/* & /api/live-chat/*
        // ================================================================
        (function initLiveChat() {
            var wrap = document.querySelector(".ut-admin-livechat");
            if (!wrap) return;

            var scope = wrap.dataset.scope || "active";
            var sessionsEl = document.getElementById("utAdminLiveChatSessions");
            var roomEmpty = document.getElementById("utAdminLiveChatRoomEmpty");
            var roomInner = document.getElementById("utAdminLiveChatRoomInner");
            var messagesEl = document.getElementById("utAdminLiveChatMessages");
            var peerName = document.getElementById("utAdminLiveChatPeerName");
            var peerStatus = document.getElementById("utAdminLiveChatPeerStatus");
            var peerAvatar = document.getElementById("utAdminLiveChatPeerAvatar");
            var composer = document.getElementById("utAdminLiveChatComposer");
            var input = document.getElementById("utAdminLiveChatInput");
            var closeBtn = document.getElementById("utAdminLiveChatClose");

            var activeSessionId = 0;
            var lastMessageId = 0;
            var sending = false;

            function fmtState(state) {
                if (state === "waiting_admin") return "Menunggu Admin";
                if (state === "admin_handling") return "Ditangani Admin";
                if (state === "ai_active") return "AI Aktif";
                if (state === "closed") return "Selesai";
                return state || "";
            }

            function liveChatAvatarHtml(m) {
                if (m.avatar_robot) {
                    return '<span class="ut-admin-livechat-avatar-sm">' +
                        '<svg class="ut-admin-livechat-avatar-robot" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
                        '<path d="M12 2a1 1 0 0 1 1 1v1h1.5A3.5 3.5 0 0 1 18 7.5V8h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1.5A3.5 3.5 0 0 1 14.5 18h-5A3.5 3.5 0 0 1 6 14.5V13H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1h1v-.5A3.5 3.5 0 0 1 9.5 4H11V3a1 1 0 0 1 1-1Zm-2.5 8a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Zm5 0a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z"/>' +
                        '</svg></span>';
                }
                var initials = escapeHtml(m.initials || "?");
                var img = m.avatar_url
                    ? '<img src="' + escapeHtml(m.avatar_url) + '" alt="' + escapeHtml(m.author_name || "") +
                      '" onerror="this.style.display=&quot;none&quot;"/>'
                    : '';
                return '<span class="ut-admin-livechat-avatar-sm">' + img +
                    '<span class="ut-admin-livechat-avatar-initials">' + initials + '</span></span>';
            }

            function liveChatRowHtml(m) {
                var meta = escapeHtml(m.author_name || "") + (m.time ? " · " + escapeHtml(m.time) : "");
                return liveChatAvatarHtml(m) +
                    '<div class="ut-admin-livechat-bubble">' +
                        '<div class="ut-admin-livechat-bubble-body">' + escapeHtml(m.body || "").replace(/\n/g, "<br/>") + '</div>' +
                        '<div class="ut-admin-livechat-bubble-meta">' + meta + '</div>' +
                    '</div>';
            }

            function liveChatRowClass(m) {
                var mine = m.author_type === "admin";
                return "ut-admin-livechat-msg " + (mine ? "ut-is-mine" : "ut-is-theirs") +
                    (m.author_type === "ai" ? " ut-is-ai" : "");
            }

            function renderMessages(messages) {
                messagesEl.innerHTML = "";
                (messages || []).forEach(function (m) {
                    var row = document.createElement("div");
                    row.className = liveChatRowClass(m);
                    row.innerHTML = liveChatRowHtml(m);
                    messagesEl.appendChild(row);
                    if (m.id && m.id > lastMessageId) lastMessageId = m.id;
                });
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }

            function appendMessages(messages) {
                var added = false;
                (messages || []).forEach(function (m) {
                    if (!m.id || m.id <= lastMessageId) return;
                    var row = document.createElement("div");
                    row.className = liveChatRowClass(m);
                    row.innerHTML = liveChatRowHtml(m);
                    messagesEl.appendChild(row);
                    lastMessageId = m.id;
                    added = true;
                });
                if (added) messagesEl.scrollTop = messagesEl.scrollHeight;
            }

            function markActiveSession() {
                sessionsEl.querySelectorAll(".ut-admin-livechat-session").forEach(function (el) {
                    el.classList.toggle("ut-is-active", String(el.dataset.sessionId) === String(activeSessionId));
                });
            }

            function openSession(sessionId) {
                if (!sessionId) return;
                activeSessionId = parseInt(sessionId, 10) || 0;
                lastMessageId = 0;
                markActiveSession();
                roomEmpty.style.display = "none";
                roomInner.style.display = "flex";
                messagesEl.innerHTML = '<div class="ut-admin-livechat-loading">Memuat pesan...</div>';
                callJsonRpc("/unitrade/admin/api/live-chat/detail", { session_id: activeSessionId })
                    .then(function (res) {
                        var data = res.result || {};
                        if (!data.ok) {
                            messagesEl.innerHTML = '<div class="ut-admin-livechat-loading">' +
                                escapeHtml(data.error || "Gagal memuat sesi.") + '</div>';
                            return;
                        }
                        var s = data.session || {};
                        peerName.textContent = s.user_name || "Customer";
                        peerStatus.textContent = fmtState(s.state) + (s.user_email ? " · " + s.user_email : "");
                        peerAvatar.textContent = s.user_initials || "?";
                        if (closeBtn) closeBtn.style.display = s.can_close ? "" : "none";
                        if (input) {
                            input.disabled = s.state === "closed";
                            input.placeholder = s.state === "closed"
                                ? "Sesi sudah ditutup."
                                : "Tulis balasan untuk user...";
                        }
                        renderMessages(data.messages);
                        // Sesi masih menunggu -> ambil alih otomatis (notif user + admin_handling).
                        if (s.state === "waiting_admin") {
                            callJsonRpc("/unitrade/admin/api/cs/start", { session_id: activeSessionId })
                                .then(function (sr) {
                                    if (sr && sr.result && sr.result.success) {
                                        peerStatus.textContent = "Ditangani Admin" +
                                            (s.user_email ? " · " + s.user_email : "");
                                        // muat ulang pesan agar notif sambutan tampil
                                        callJsonRpc("/unitrade/admin/api/live-chat/detail", { session_id: activeSessionId })
                                            .then(function (d2) {
                                                if (d2 && d2.result && d2.result.ok) appendMessages(d2.result.messages);
                                            });
                                        refreshSessionList();
                                    }
                                });
                        }
                    });
            }

            function refreshSessionList() {
                callJsonRpc("/unitrade/admin/api/live-chat/sessions", { scope: scope })
                    .then(function (res) {
                        var data = res.result || {};
                        var rows = data.sessions || [];
                        if (!rows.length) {
                            sessionsEl.innerHTML = '<div class="ut-admin-livechat-empty">Belum ada percakapan live chat.</div>';
                            return;
                        }
                        var html = "";
                        rows.forEach(function (s) {
                            html +=
                                '<button type="button" class="ut-admin-livechat-session' +
                                    (String(s.id) === String(activeSessionId) ? ' ut-is-active' : '') +
                                    '" data-session-id="' + s.id + '">' +
                                    '<span class="ut-admin-livechat-avatar">' + escapeHtml(s.user_initials || "?") + '</span>' +
                                    '<span class="ut-admin-livechat-session-body">' +
                                        '<span class="ut-admin-livechat-session-top">' +
                                            '<span class="ut-admin-livechat-name">' + escapeHtml(s.user_name || "Customer") + '</span>' +
                                            '<span class="ut-admin-livechat-time">' + escapeHtml(s.last_activity || "") + '</span>' +
                                        '</span>' +
                                        '<span class="ut-admin-livechat-preview">' + escapeHtml(s.preview || "") + '</span>' +
                                        '<span class="ut-admin-livechat-badge ut-admin-livechat-badge-' + escapeHtml(s.state) + '">' +
                                            escapeHtml(s.state_label || "") + '</span>' +
                                    '</span>' +
                                '</button>';
                        });
                        sessionsEl.innerHTML = html;
                    });
            }

            // Click sesi -> buka room
            sessionsEl.addEventListener("click", function (e) {
                var item = e.target.closest(".ut-admin-livechat-session");
                if (!item) return;
                openSession(item.dataset.sessionId);
            });

            // Kirim balasan
            if (composer) {
                composer.addEventListener("submit", function (e) {
                    e.preventDefault();
                    if (!activeSessionId || sending) return;
                    var body = (input.value || "").trim();
                    if (!body) return;
                    sending = true;
                    input.disabled = true;
                    callJsonRpc("/unitrade/admin/api/cs/reply", {
                        session_id: activeSessionId,
                        body: body,
                    }).then(function (res) {
                        sending = false;
                        input.disabled = false;
                        var r = res.result || {};
                        if (r.success) {
                            input.value = "";
                            appendMessages([r.message]);
                            input.focus();
                        } else {
                            showToast(r.message || "Gagal mengirim balasan.", "error");
                        }
                    }).catch(function () {
                        sending = false;
                        input.disabled = false;
                        showToast("Gagal mengirim balasan.", "error");
                    });
                });
                // Enter untuk kirim, Shift+Enter untuk baris baru
                input.addEventListener("keydown", function (e) {
                    if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        composer.dispatchEvent(new Event("submit", { cancelable: true }));
                    }
                });
            }

            // Tutup sesi
            if (closeBtn) {
                closeBtn.addEventListener("click", async function () {
                    if (!activeSessionId) return;
                    if (!await confirmAdmin("Akhiri sesi live chat ini? User akan kembali terhubung dengan AI Assistant.", { title: "Akhiri Chat" })) return;
                    callJsonRpc("/unitrade/admin/api/cs/close", { session_id: activeSessionId })
                        .then(function (res) {
                            var r = res.result || {};
                            if (r.success) {
                                showToast("Sesi ditutup.", "success");
                                openSession(activeSessionId);
                                refreshSessionList();
                            } else {
                                showToast(r.message || "Gagal menutup sesi.", "error");
                            }
                        });
                });
            }

            // Polling: pesan baru pada sesi aktif + refresh daftar
            setInterval(function () {
                if (activeSessionId) {
                    callJsonRpc("/unitrade/admin/api/live-chat/detail", { session_id: activeSessionId })
                        .then(function (res) {
                            var data = res.result || {};
                            if (data.ok) appendMessages(data.messages);
                        });
                }
            }, 5000);
            setInterval(refreshSessionList, 15000);

            // Auto-buka sesi dari query (?session_id=) bila ada
            var initial = parseInt(wrap.dataset.initialSession, 10) || 0;
            if (initial) openSession(initial);
        })();
    });
})();
