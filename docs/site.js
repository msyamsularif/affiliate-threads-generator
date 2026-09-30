// Shared by every page of this site: apply the stored theme (or the system
// preference) before first paint, then wire up the masthead toggle.
(function () {
    var root = document.documentElement;
    var stored = null;
    try {
        stored = localStorage.getItem("theme");
    } catch (error) { }
    var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var theme =
        stored === "dark" || stored === "light"
            ? stored
            : prefersDark
                ? "dark"
                : "light";
    root.setAttribute("data-theme", theme);

    function wireToggle() {
        var button = document.getElementById("theme");
        if (!button) {
            return;
        }
        function sync() {
            button.setAttribute(
                "aria-pressed",
                root.getAttribute("data-theme") === "dark" ? "true" : "false",
            );
        }
        button.addEventListener("click", function () {
            var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
            root.setAttribute("data-theme", next);
            try {
                localStorage.setItem("theme", next);
            } catch (error) { }
            sync();
        });
        sync();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", wireToggle);
    } else {
        wireToggle();
    }
})();
