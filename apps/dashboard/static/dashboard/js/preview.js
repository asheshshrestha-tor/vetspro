(function () {
  "use strict";

  // Links marked data-preview open in a pop-up instead of a new page.
  //   data-preview          a page (invoice, receipt, visit summary, printed form)
  //   data-preview="image"  a picture or X-ray, shown fitted on a dark background
  //   data-preview="pdf"    a PDF, shown in the browser's own viewer (which has its own print button)
  // data-preview-title sets the heading; otherwise the link's text is used.
  // Ctrl/Cmd/Shift-click and middle-click still open the link the usual way.
  var element = document.getElementById("preview_modal");
  if (!element || !window.bootstrap) return;

  var modal = bootstrap.Modal.getOrCreateInstance(element);
  var frame = element.querySelector("[data-preview-frame]");
  var title = element.querySelector(".modal-title");
  var loading = element.querySelector("[data-preview-loading]");
  var printButton = element.querySelector("[data-preview-print]");
  var openLink = element.querySelector("[data-preview-open]");
  var downloadLink = element.querySelector("[data-preview-download]");

  function escapeAttribute(value) {
    return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }

  function imagePage(url) {
    return "<!DOCTYPE html><html><head><style>" +
      "html,body{margin:0;height:100%;background:#15181e}" +
      "body{display:flex;align-items:center;justify-content:center}" +
      "img{max-width:100%;max-height:100%;object-fit:contain}" +
      "@media print{html,body{background:#fff;height:auto}}" +
      "</style></head><body><img src=\"" + escapeAttribute(url) + "\" alt=\"\"></body></html>";
  }

  function open(link) {
    var url = link.href;
    var kind = link.getAttribute("data-preview") || "page";

    title.textContent = link.getAttribute("data-preview-title") || link.textContent.trim() || link.title || "Preview";
    openLink.href = url;
    downloadLink.href = url;
    downloadLink.classList.toggle("d-none", kind === "page");
    printButton.classList.toggle("d-none", kind === "pdf");
    loading.classList.remove("d-none");

    frame.removeAttribute("srcdoc");
    frame.removeAttribute("src");
    if (kind === "image") {
      frame.srcdoc = imagePage(url);
    } else {
      frame.src = url;
    }
    modal.show();
  }

  frame.addEventListener("load", function () {
    loading.classList.add("d-none");
  });

  printButton.addEventListener("click", function () {
    try {
      frame.contentWindow.focus();
      frame.contentWindow.print();
    } catch (error) {
      window.open(openLink.href, "_blank", "noopener");
    }
  });

  // Free the page and stop any loading once the pop-up is closed.
  element.addEventListener("hidden.bs.modal", function () {
    frame.removeAttribute("srcdoc");
    frame.removeAttribute("src");
  });

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-preview]");
    if (!link || event.defaultPrevented) return;
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    open(link);
  });
})();
