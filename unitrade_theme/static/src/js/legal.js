(function () {
    "use strict";

    var initialized = false;

    function setActiveNav(activeId) {
        document.querySelectorAll("[data-legal-nav]").forEach(function (link) {
            link.classList.toggle("is-active", link.dataset.legalNav === activeId);
        });
    }

    function openInitialSection(root) {
        var activeAnchor = root.dataset.activeAnchor || "faq";
        var hash = window.location.hash ? window.location.hash.replace("#", "") : activeAnchor;
        setActiveNav(hash === "terms" ? "terms" : "faq");
        if (window.location.hash || activeAnchor === "terms") {
            var target = document.getElementById(hash);
            if (target) {
                window.setTimeout(function () {
                    target.scrollIntoView({ behavior: "smooth", block: "start" });
                }, 120);
            }
        }
    }

    function setAccordionState(accordion, isOpen) {
        var trigger = accordion.querySelector(".ut-legal-accordion-trigger");
        var panel = accordion.querySelector(".ut-legal-accordion-panel");
        accordion.classList.toggle("is-open", isOpen);
        if (trigger) {
            trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }
        if (panel) {
            panel.toggleAttribute("hidden", !isOpen);
        }
    }

    function setupAccordion(root) {
        root.querySelectorAll("[data-legal-accordion]").forEach(function (accordion) {
            setAccordionState(accordion, accordion.classList.contains("is-open"));
        });

        root.addEventListener("click", function (event) {
            var trigger = event.target.closest(".ut-legal-accordion-trigger");
            if (!trigger || !root.contains(trigger)) {
                return;
            }
            var accordion = trigger.closest("[data-legal-accordion]");
            if (!accordion) {
                return;
            }
            setAccordionState(accordion, !accordion.classList.contains("is-open"));
        });
    }

    function setupNavigation() {
        document.querySelectorAll("[data-legal-nav]").forEach(function (link) {
            link.addEventListener("click", function (event) {
                var targetId = link.dataset.legalNav;
                var target = document.getElementById(targetId);
                if (!target) {
                    return;
                }
                event.preventDefault();
                history.replaceState(null, "", "#" + targetId);
                setActiveNav(targetId);
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });

        var sections = Array.prototype.slice.call(document.querySelectorAll("[data-legal-section]"));
        if (!sections.length || !("IntersectionObserver" in window)) {
            return;
        }
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    setActiveNav(entry.target.dataset.legalSection);
                }
            });
        }, {
            rootMargin: "-30% 0px -55% 0px",
            threshold: 0.01,
        });
        sections.forEach(function (section) {
            observer.observe(section);
        });
    }

    function initLegalPage() {
        if (initialized) {
            return;
        }
        var root = document.querySelector(".ut-legal-page");
        if (!root) {
            return;
        }
        initialized = true;
        setupAccordion(root);
        setupNavigation();
        openInitialSection(root);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initLegalPage);
    } else {
        initLegalPage();
    }
})();
