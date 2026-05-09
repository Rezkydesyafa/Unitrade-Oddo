(function () {
    "use strict";

    function onReady(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
            return;
        }
        callback();
    }

    function resizeCanvas(canvas) {
        var parent = canvas.parentElement;
        var rect = parent ? parent.getBoundingClientRect() : canvas.getBoundingClientRect();
        var ratio = window.devicePixelRatio || 1;
        var width = Math.max(320, Math.floor(rect.width));
        var height = Math.max(240, Math.floor(rect.height || 290));
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = width + "px";
        canvas.style.height = height + "px";
        return {
            ratio: ratio,
            width: width,
            height: height,
        };
    }

    function formatCompact(value) {
        var number = Number(value || 0);
        if (number >= 1000000000) {
            return "Rp " + (number / 1000000000).toFixed(1) + "M";
        }
        if (number >= 1000000) {
            return "Rp " + (number / 1000000).toFixed(1) + "jt";
        }
        if (number >= 1000) {
            return "Rp " + Math.round(number / 1000) + "rb";
        }
        return "Rp " + Math.round(number);
    }

    function drawLineChart(canvas, chartData, period) {
        if (!canvas || !canvas.getContext) {
            return;
        }
        var data = chartData[period] || chartData.weekly || {};
        var labels = data.labels || [];
        var revenue = data.revenue || [];
        var orders = data.orders || [];
        var ctx = canvas.getContext("2d");
        var size = resizeCanvas(canvas);
        var ratio = size.ratio;
        var width = size.width;
        var height = size.height;
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.clearRect(0, 0, width, height);

        var pad = {
            top: 22,
            right: 22,
            bottom: 42,
            left: 64,
        };
        var plotWidth = Math.max(1, width - pad.left - pad.right);
        var plotHeight = Math.max(1, height - pad.top - pad.bottom);
        var maxRevenue = Math.max.apply(null, revenue.concat([0]));
        var maxOrders = Math.max.apply(null, orders.concat([0]));
        var maxValue = Math.max(maxRevenue, maxOrders * Math.max(maxRevenue / Math.max(maxOrders, 1), 1), 1);
        var stepCount = 4;

        ctx.font = "600 12px Urbanist, Inter, sans-serif";
        ctx.textBaseline = "middle";
        ctx.strokeStyle = "#eceef2";
        ctx.lineWidth = 1;
        ctx.fillStyle = "#6a7686";

        for (var i = 0; i <= stepCount; i += 1) {
            var y = pad.top + (plotHeight / stepCount) * i;
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(width - pad.right, y);
            ctx.stroke();
            var value = maxValue - (maxValue / stepCount) * i;
            ctx.fillText(formatCompact(value), 8, y);
        }

        if (!labels.length) {
            ctx.fillStyle = "#6a7686";
            ctx.textAlign = "center";
            ctx.fillText("Belum ada data penjualan", width / 2, height / 2);
            return;
        }

        var gap = labels.length > 1 ? plotWidth / (labels.length - 1) : plotWidth;
        var points = revenue.map(function (value, index) {
            var x = pad.left + gap * index;
            var y = pad.top + plotHeight - (Number(value || 0) / maxValue) * plotHeight;
            return {
                x: x,
                y: y,
                value: value,
            };
        });

        ctx.textAlign = "center";
        ctx.fillStyle = "#6a7686";
        labels.forEach(function (label, index) {
            var x = pad.left + gap * index;
            ctx.fillText(label, x, height - 18);
        });

        if (orders.length) {
            var barWidth = Math.max(8, Math.min(26, gap * 0.26));
            var orderMax = Math.max.apply(null, orders.concat([1]));
            ctx.fillStyle = "rgba(237, 107, 96, 0.18)";
            orders.forEach(function (value, index) {
                var x = pad.left + gap * index - barWidth / 2;
                var barHeight = (Number(value || 0) / orderMax) * (plotHeight * 0.42);
                ctx.fillRect(x, pad.top + plotHeight - barHeight, barWidth, barHeight);
            });
        }

        if (points.length) {
            var gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotHeight);
            gradient.addColorStop(0, "rgba(41, 41, 41, 0.16)");
            gradient.addColorStop(1, "rgba(41, 41, 41, 0)");
            ctx.beginPath();
            points.forEach(function (point, index) {
                if (index === 0) {
                    ctx.moveTo(point.x, point.y);
                } else {
                    ctx.lineTo(point.x, point.y);
                }
            });
            ctx.lineTo(points[points.length - 1].x, pad.top + plotHeight);
            ctx.lineTo(points[0].x, pad.top + plotHeight);
            ctx.closePath();
            ctx.fillStyle = gradient;
            ctx.fill();

            ctx.beginPath();
            points.forEach(function (point, index) {
                if (index === 0) {
                    ctx.moveTo(point.x, point.y);
                } else {
                    ctx.lineTo(point.x, point.y);
                }
            });
            ctx.strokeStyle = "#292929";
            ctx.lineWidth = 3;
            ctx.lineJoin = "round";
            ctx.lineCap = "round";
            ctx.stroke();

            points.forEach(function (point) {
                ctx.beginPath();
                ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
                ctx.fillStyle = "#ffffff";
                ctx.fill();
                ctx.strokeStyle = "#292929";
                ctx.lineWidth = 2;
                ctx.stroke();
            });
        }
    }

    function initChart(page) {
        var canvas = page.querySelector("[data-dashboard-chart]");
        if (!canvas) {
            return;
        }
        var chartData = {};
        try {
            chartData = JSON.parse(page.getAttribute("data-chart") || "{}");
        } catch (error) {
            chartData = {};
        }
        var period = "weekly";
        var redraw = function () {
            drawLineChart(canvas, chartData, period);
        };
        page.querySelectorAll("[data-dashboard-chart-period]").forEach(function (button) {
            button.addEventListener("click", function () {
                period = button.getAttribute("data-dashboard-chart-period") || "weekly";
                page.querySelectorAll("[data-dashboard-chart-period]").forEach(function (item) {
                    item.classList.toggle("active", item === button);
                });
                redraw();
            });
        });
        var resizeTimer = null;
        window.addEventListener("resize", function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(redraw, 120);
        });
        redraw();
    }

    function initSidebar(page) {
        var openButtons = page.querySelectorAll("[data-dashboard-sidebar-toggle]");
        var closeButtons = page.querySelectorAll("[data-dashboard-sidebar-close]");
        var open = function () {
            page.classList.add("sidebar-open");
        };
        var close = function () {
            page.classList.remove("sidebar-open");
        };
        openButtons.forEach(function (button) {
            button.addEventListener("click", open);
        });
        closeButtons.forEach(function (button) {
            button.addEventListener("click", close);
        });
        page.querySelectorAll("[data-dashboard-nav]").forEach(function (link) {
            link.addEventListener("click", function (event) {
                var href = link.getAttribute("href") || "";
                if (href.charAt(0) !== "#") {
                    return;
                }
                var target = page.querySelector(href);
                if (!target) {
                    return;
                }
                event.preventDefault();
                page.querySelectorAll("[data-dashboard-nav]").forEach(function (item) {
                    item.classList.toggle("active", item === link);
                });
                target.scrollIntoView({
                    block: "start",
                    behavior: "smooth",
                });
                close();
            });
        });
    }

    function initSearch(page) {
        var modal = page.querySelector(".ut-dash-search-modal");
        var input = page.querySelector("[data-dashboard-search-input]");
        var empty = page.querySelector("[data-dashboard-search-empty]");
        if (!modal || !input) {
            return;
        }
        var items = Array.prototype.slice.call(page.querySelectorAll("[data-dashboard-search-item]"));
        var applyFilter = function () {
            var query = input.value.trim().toLowerCase();
            var visible = 0;
            items.forEach(function (item) {
                var matches = !query || item.textContent.toLowerCase().indexOf(query) !== -1;
                item.hidden = !matches;
                if (matches) {
                    visible += 1;
                }
            });
            if (empty) {
                empty.classList.toggle("visible", visible === 0);
            }
        };
        var open = function () {
            modal.classList.add("open");
            modal.setAttribute("aria-hidden", "false");
            input.value = "";
            applyFilter();
            window.setTimeout(function () {
                input.focus();
            }, 20);
        };
        var close = function () {
            modal.classList.remove("open");
            modal.setAttribute("aria-hidden", "true");
        };
        page.querySelectorAll("[data-dashboard-search-open]").forEach(function (button) {
            button.addEventListener("click", open);
        });
        page.querySelectorAll("[data-dashboard-search-close]").forEach(function (button) {
            button.addEventListener("click", close);
        });
        input.addEventListener("input", applyFilter);
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && modal.classList.contains("open")) {
                close();
            }
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                open();
            }
        });
    }

    onReady(function () {
        var page = document.querySelector(".ut-seller-dashboard-page");
        if (!page) {
            return;
        }
        initSidebar(page);
        initSearch(page);
        initChart(page);
    });
}());
