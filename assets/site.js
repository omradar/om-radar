(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- recherche (page d'accueil) ---- */
  var bar = document.getElementById("searchbar"), sbtn = document.getElementById("open-search"), q = document.getElementById("q");
  if (bar && sbtn && q) {
    sbtn.addEventListener("click", function () {
      bar.hidden = !bar.hidden;
      sbtn.setAttribute("aria-expanded", String(!bar.hidden));
      if (!bar.hidden) q.focus();
    });
    q.addEventListener("input", function () {
      var t = q.value.trim().toLowerCase();
      document.querySelectorAll("#list-une li, #list-mercato li, #list-latest li").forEach(function (li) {
        li.hidden = t !== "" && li.textContent.toLowerCase().indexOf(t) === -1;
      });
    });
  }

  /* ---- menu ---- */
  var drawer = document.getElementById("drawer"), mbtn = document.getElementById("open-menu"), mclose = document.getElementById("close-menu");
  function setMenu(open) {
    if (!drawer) return;
    drawer.hidden = !open;
    mbtn.setAttribute("aria-expanded", String(open));
    document.body.style.overflow = open ? "hidden" : "";
    (open ? mclose : mbtn).focus();
  }
  if (drawer && mbtn && mclose) {
    mbtn.addEventListener("click", function () { setMenu(drawer.hidden); });
    mclose.addEventListener("click", function () { setMenu(false); });
    drawer.addEventListener("click", function (e) {
      if (e.target === drawer || (e.target.closest && e.target.closest("nav a"))) setMenu(false);
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !drawer.hidden) setMenu(false); });
  }

  /* ---- carrousel de la une ---- */
  var car = document.getElementById("carousel");
  if (car) {
    var track = car.querySelector(".track"), slides = track.children, n = slides.length;
    var count = car.querySelector(".count"), idx = 0, timer = null, paused = false;
    function show(i) {
      idx = (i + n) % n;
      track.scrollTo({ left: idx * track.clientWidth, behavior: reduce ? "auto" : "smooth" });
    }
    function sync() {
      var i = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
      if (i !== idx || count) { idx = i; if (count) count.textContent = (idx + 1) + " / " + n; }
    }
    track.addEventListener("scroll", sync, { passive: true });
    window.addEventListener("resize", function () { track.scrollTo({ left: idx * track.clientWidth }); });
    var prev = car.querySelector(".prev"), next = car.querySelector(".next");
    if (prev) prev.addEventListener("click", function () { show(idx - 1); });
    if (next) next.addEventListener("click", function () { show(idx + 1); });
    car.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") show(idx - 1);
      if (e.key === "ArrowRight") show(idx + 1);
    });
    if (n > 1 && !reduce) {
      var stop = function () { paused = true; };
      var go = function () { paused = false; };
      ["mouseenter", "focusin", "touchstart"].forEach(function (ev) { car.addEventListener(ev, stop, { passive: true }); });
      ["mouseleave", "focusout", "touchend"].forEach(function (ev) { car.addEventListener(ev, go, { passive: true }); });
      timer = setInterval(function () { if (!paused && document.visibilityState === "visible") show(idx + 1); }, 6500);
    }
  }

  /* ---- rubrique active pendant le défilement (accueil) ---- */
  var links = document.querySelectorAll(".nav a, .chips a");
  if ("IntersectionObserver" in window && document.getElementById("actualites")) {
    var map = {};
    links.forEach(function (a) {
      var h = a.getAttribute("href"); map[h] = (map[h] || []).concat(a);
    });
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) {
          links.forEach(function (a) { a.classList.remove("on"); });
          (map["#" + e.target.id] || []).forEach(function (a) { a.classList.add("on"); });
        }
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    ["actualites", "mercato", "matchs", "analyses"].forEach(function (id) {
      var el = document.getElementById(id); if (el) io.observe(el);
    });
  }
})();
