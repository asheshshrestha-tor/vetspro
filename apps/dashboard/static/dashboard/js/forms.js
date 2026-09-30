(function () {
  "use strict";

  // Fill in the slug from the title or name until the slug is edited by hand.
  var slug = document.querySelector("input[name=slug]");
  var source = document.querySelector("input[name=title], input[name=name]");
  if (slug && source && !slug.value) {
    var touched = false;
    slug.addEventListener("input", function () { touched = true; });
    source.addEventListener("input", function () {
      if (touched) return;
      slug.value = source.value
        .toLowerCase()
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/&/g, " and ")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, slug.maxLength > 0 ? slug.maxLength : 100);
    });
  }

  // Settings that only apply to some value types are hidden for the others.
  var kindSelect = document.querySelector('select[name="value_kind"]');
  var dependents = document.querySelectorAll("[data-show-for-kind]");
  if (kindSelect && dependents.length) {
    var applyKind = function () {
      dependents.forEach(function (input) {
        var row = input.closest(".row") || input.parentElement;
        var kinds = input.getAttribute("data-show-for-kind").split(" ");
        row.classList.toggle("d-none", kinds.indexOf(kindSelect.value) === -1);
      });
    };
    kindSelect.addEventListener("change", applyKind);
    applyKind();
  }

  // Search-as-you-type dropdowns. "data-forward" lists other fields whose values are
  // sent with each search, and changing one of them clears this dropdown.
  function initAutocomplete(scope) {
    if (!window.jQuery || !jQuery.fn.select2) return;
    scope.querySelectorAll("select[data-autocomplete-url]").forEach(function (select) {
      if (select.classList.contains("select2-hidden-accessible")) return;
      var $select = jQuery(select);
      var forward = (select.getAttribute("data-forward") || "").split(",").filter(Boolean);
      var form = select.form || document;

      function source(name) {
        return form.querySelector('[name="' + name + '"]');
      }

      $select.select2({
        allowClear: !select.required,
        placeholder: select.getAttribute("data-placeholder") || "",
        ajax: {
          url: select.getAttribute("data-autocomplete-url"),
          dataType: "json",
          delay: 200,
          data: function (params) {
            var query = { q: params.term || "" };
            forward.forEach(function (name) {
              var field = source(name);
              query[name] = field ? field.value : "";
            });
            return query;
          },
          processResults: function (data) {
            return { results: data.results };
          }
        }
      });

      forward.forEach(function (name) {
        var field = source(name);
        if (field) {
          jQuery(field).on("change", function () {
            $select.val(null).trigger("change");
          });
        }
      });
    });
  }
  window.dashboardInitAutocomplete = initAutocomplete;
  initAutocomplete(document);

  // Inline rows: add new ones, and mark rows that will be removed on save.
  document.querySelectorAll("[data-inline]").forEach(function (card) {
    var prefix = card.getAttribute("data-inline");
    var rows = card.querySelector("[data-inline-rows]");
    var template = card.querySelector("[data-inline-template]");
    var total = card.querySelector("#id_" + prefix + "-TOTAL_FORMS");
    var addButton = card.querySelector("[data-inline-add]");
    if (!rows || !template || !total || !addButton) return;

    addButton.addEventListener("click", function () {
      var index = parseInt(total.value, 10);
      var holder = document.createElement("tbody");
      holder.innerHTML = template.innerHTML.replace(/__prefix__/g, String(index));
      var row = holder.querySelector("tr");
      if (!row) return;
      rows.appendChild(row);
      total.value = String(index + 1);
      initAutocomplete(row);
      row.dispatchEvent(new CustomEvent("inline:added", { bubbles: true }));
      var first = row.querySelector("input:not([type=hidden]), textarea, select");
      if (first) first.focus();
    });

    rows.addEventListener("change", function (event) {
      var box = event.target;
      if (!box.name || !/-DELETE$/.test(box.name)) return;
      var row = box.closest("[data-inline-row]");
      if (row) row.classList.toggle("inline-row--removed", box.checked);
    });
  });
})();
