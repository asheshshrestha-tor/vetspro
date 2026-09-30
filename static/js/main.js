(function () {
  "use strict";

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initNav() {
    var toggle = document.querySelector(".nav-toggle");
    var nav = document.getElementById("site-nav");
    if (!toggle || !nav) return;

    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  }

  function initSlider() {
    var slider = document.querySelector("[data-slider]");
    if (!slider) return;
    var slides = slider.querySelectorAll("[data-slide]");
    if (slides.length < 2) return;

    var index = 0;
    var timer = null;

    function show(next) {
      slides[index].classList.remove("is-active");
      index = (next + slides.length) % slides.length;
      slides[index].classList.add("is-active");
    }

    function start() {
      if (reducedMotion) return;
      stop();
      timer = window.setInterval(function () { show(index + 1); }, 6000);
    }

    function stop() {
      if (timer) window.clearInterval(timer);
      timer = null;
    }

    var prev = slider.querySelector("[data-slider-prev]");
    var next = slider.querySelector("[data-slider-next]");
    if (prev) prev.addEventListener("click", function () { show(index - 1); start(); });
    if (next) next.addEventListener("click", function () { show(index + 1); start(); });

    slider.addEventListener("mouseenter", stop);
    slider.addEventListener("mouseleave", start);
    slider.addEventListener("focusin", stop);
    slider.addEventListener("focusout", start);
    start();
  }

  function initCarousel() {
    document.querySelectorAll("[data-carousel]").forEach(function (carousel) {
      var track = carousel.querySelector("[data-carousel-track]");
      if (!track) return;

      function move(direction) {
        var card = track.firstElementChild;
        if (!card) return;
        var gap = parseFloat(window.getComputedStyle(track).columnGap) || 0;
        track.scrollBy({ left: direction * (card.offsetWidth + gap), behavior: reducedMotion ? "auto" : "smooth" });
      }

      var prev = carousel.querySelector("[data-carousel-prev]");
      var next = carousel.querySelector("[data-carousel-next]");
      if (prev) prev.addEventListener("click", function () { move(-1); });
      if (next) next.addEventListener("click", function () { move(1); });
    });
  }

  function animateCounter(el) {
    var target = parseInt(el.getAttribute("data-counter"), 10);
    if (isNaN(target) || reducedMotion) return;

    var duration = 1400;
    var startTime = null;

    function step(now) {
      if (startTime === null) startTime = now;
      var progress = Math.min((now - startTime) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = String(Math.round(target * eased));
      if (progress < 1) window.requestAnimationFrame(step);
    }

    el.textContent = "0";
    window.requestAnimationFrame(step);
  }

  function initOnScroll() {
    var reveals = document.querySelectorAll(".reveal");
    var counters = document.querySelectorAll("[data-counter]");

    if (!("IntersectionObserver" in window)) {
      reveals.forEach(function (el) { el.classList.add("is-visible"); });
      return;
    }

    var revealObserver = new IntersectionObserver(function (entries, observer) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12 });
    reveals.forEach(function (el) { revealObserver.observe(el); });

    var counterObserver = new IntersectionObserver(function (entries, observer) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        animateCounter(entry.target);
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.6 });
    counters.forEach(function (el) { counterObserver.observe(el); });
  }

  function initGallery() {
    var gallery = document.querySelector("[data-gallery]");
    var lightbox = document.querySelector("[data-lightbox]");
    if (!gallery || !lightbox || typeof lightbox.showModal !== "function") return;

    var items = Array.prototype.slice.call(gallery.querySelectorAll("[data-gallery-item]"));
    var image = lightbox.querySelector("[data-lightbox-image]");
    var caption = lightbox.querySelector("[data-lightbox-caption]");
    var current = 0;

    function show(i) {
      current = (i + items.length) % items.length;
      var title = items[current].getAttribute("data-title") || "";
      image.src = items[current].href;
      image.alt = title;
      caption.textContent = title;
    }

    items.forEach(function (item, i) {
      item.addEventListener("click", function (event) {
        event.preventDefault();
        show(i);
        lightbox.showModal();
      });
    });

    lightbox.querySelector("[data-lightbox-close]").addEventListener("click", function () { lightbox.close(); });
    lightbox.querySelector("[data-lightbox-prev]").addEventListener("click", function () { show(current - 1); });
    lightbox.querySelector("[data-lightbox-next]").addEventListener("click", function () { show(current + 1); });

    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox) lightbox.close();
    });
    lightbox.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") show(current - 1);
      if (event.key === "ArrowRight") show(current + 1);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initNav();
    initSlider();
    initCarousel();
    initOnScroll();
    initGallery();
  });
})();
