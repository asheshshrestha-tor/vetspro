(function () {
  "use strict";

  // Cancelling asks for an optional reason, which is kept on the appointment.
  document.querySelectorAll("form[data-cancel-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var reason = window.prompt("Cancel this appointment? You can add a reason (optional).", "");
      if (reason === null) {
        event.preventDefault();
        return;
      }
      form.querySelector('input[name="reason"]').value = reason;
    });
  });

  // Walk-in: an existing owner hides the new-owner fields, and a chosen pet hides the new-pet fields.
  var walkIn = document.querySelector("form[data-walk-in]");
  if (walkIn && window.jQuery) {
    var client = walkIn.querySelector('select[name="client"]');
    var pet = walkIn.querySelector('select[name="pet"]');
    var newClient = walkIn.querySelector("[data-new-client]");
    var existingPet = walkIn.querySelector("[data-existing-pet]");
    var newPet = walkIn.querySelector("[data-new-pet]");

    var refresh = function () {
      var hasClient = Boolean(client.value);
      var hasPet = Boolean(pet.value);
      newClient.classList.toggle("d-none", hasClient);
      existingPet.classList.toggle("d-none", !hasClient);
      newPet.classList.toggle("d-none", hasClient && hasPet);
    };
    // Returning owners usually bring a pet already on record: pick it when there is only one.
    var selectOnlyPet = function () {
      if (!client.value || pet.value) return;
      var url = pet.getAttribute("data-autocomplete-url") + "?client=" + encodeURIComponent(client.value);
      fetch(url, { credentials: "same-origin" })
        .then(function (response) { return response.ok ? response.json() : { results: [] }; })
        .then(function (data) {
          if (data.results.length === 1 && !pet.value) {
            var only = data.results[0];
            jQuery(pet).append(new Option(only.text, only.id, true, true)).trigger("change");
          }
        });
    };

    jQuery(client).on("change", function () {
      refresh();
      selectOnlyPet();
    });
    jQuery(pet).on("change", refresh);
    refresh();
  }

  // A link can open a tab directly, e.g. …/#exam opens the examination tab.
  if (window.bootstrap && window.location.hash) {
    var hashTab = document.querySelector('[data-bs-toggle="tab"][data-bs-target="#tab-' + window.location.hash.slice(1) + '"]');
    if (hashTab) bootstrap.Tab.getOrCreateInstance(hashTab).show();
  }

  // Consultation: open the first tab that has an error, so it is not missed.
  var consultation = document.querySelector("form[data-consultation]");
  if (consultation && window.bootstrap) {
    var error = consultation.querySelector(".invalid-feedback, .alert-danger");
    var pane = error && error.closest(".tab-pane");
    if (pane) {
      var trigger = document.querySelector('[data-bs-target="#' + pane.id + '"]');
      if (trigger) bootstrap.Tab.getOrCreateInstance(trigger).show();
    }
    document.querySelectorAll(".tab-pane").forEach(function (tabPane) {
      if (tabPane.querySelector(".invalid-feedback")) {
        var tab = document.querySelector('[data-bs-target="#' + tabPane.id + '"]');
        if (tab) tab.classList.add("text-danger");
      }
    });
  }

  // History and examination: flag values outside the normal range while typing.
  document.querySelectorAll("tr[data-value-row]").forEach(function (row) {
    var input = row.querySelector("input, select");
    var flag = row.querySelector("[data-value-flag]");
    if (!input || !flag) return;
    var kind = row.getAttribute("data-kind");

    var check = function () {
      var value = (input.value || "").trim();
      var abnormal = false;
      if (value && kind === "number") {
        var number = parseFloat(value);
        var min = parseFloat(row.getAttribute("data-min"));
        var max = parseFloat(row.getAttribute("data-max"));
        abnormal = !isNaN(number) && ((!isNaN(min) && number < min) || (!isNaN(max) && number > max));
      } else if (value && (kind === "choice" || kind === "yesno")) {
        var normal = (row.getAttribute("data-normal") || "").split("|").filter(Boolean).map(function (v) {
          return v.toLowerCase();
        });
        abnormal = normal.length > 0 && normal.indexOf(value.toLowerCase()) === -1;
      }
      flag.classList.toggle("d-none", !abnormal);
      input.classList.toggle("border-danger", abnormal);
    };
    input.addEventListener("input", check);
    input.addEventListener("change", check);
    check();
  });

  // Vaccination: "Today" records a dose given at this visit, and the next due date
  // is suggested from the vaccine's booster interval.
  var visitDateData = document.getElementById("visit-date-data");
  var visitDate = visitDateData ? JSON.parse(visitDateData.textContent) : "";
  var pad = function (n) { return String(n).padStart(2, "0"); };
  var addDays = function (iso, days) {
    var parts = iso.split("-").map(Number);
    var date = new Date(parts[0], parts[1] - 1, parts[2] + days);
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
  };

  document.querySelectorAll("tr[data-vaccine-row]").forEach(function (row) {
    var given = row.querySelector('input[name$="-given_on"]');
    var due = row.querySelector('input[name$="-next_due_date"]');
    var today = row.querySelector("[data-given-today]");
    var booster = parseInt(row.getAttribute("data-booster"), 10);
    if (!given) return;

    var suggest = function () {
      if (due && !due.value && given.value && booster) due.value = addDays(given.value, booster);
    };
    given.addEventListener("change", suggest);
    if (today) {
      today.addEventListener("click", function () {
        given.value = visitDate;
        suggest();
      });
    }
  });

  // Treatment: picking from the catalogue fills in the usual details and price, and the
  // line amounts and total update as quantities and prices change.
  var treatmentTable = document.querySelector("[data-treatment-table]");
  if (treatmentTable) {
    var rupees = function (value) {
      return "Rs. " + value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };
    var numberIn = function (input) {
      var value = parseFloat(input && input.value);
      return isNaN(value) ? 0 : value;
    };
    var totalCell = treatmentTable.querySelector("[data-treatment-total]");

    var recalcTreatment = function () {
      var total = 0;
      treatmentTable.querySelectorAll("tr[data-treatment-line]").forEach(function (row) {
        var removed = row.querySelector('input[name$="-DELETE"]');
        var qty = numberIn(row.querySelector('input[name$="-quantity"]'));
        var price = numberIn(row.querySelector('input[name$="-unit_price"]'));
        var amount = removed && removed.checked ? 0 : qty * price;
        total += amount;
        var cell = row.querySelector("[data-line-total]");
        if (cell) cell.textContent = amount ? rupees(amount) : "";
      });
      if (totalCell) totalCell.textContent = rupees(total);
    };

    var fill = function (row, name, value, overwrite) {
      var field = row.querySelector('[name$="-' + name + '"]');
      if (field && value !== undefined && value !== null && (overwrite || !field.value)) field.value = value;
    };

    if (window.jQuery) {
      jQuery(treatmentTable).on("select2:select", 'select[name$="-item"]', function (event) {
        var data = event.params && event.params.data;
        var row = this.closest("tr[data-treatment-line]");
        if (!row || !data) return;
        fill(row, "name", data.name, true);
        fill(row, "kind", data.kind, true);
        fill(row, "dose", data.dose, true);
        fill(row, "route", data.route, true);
        fill(row, "frequency", data.frequency, true);
        fill(row, "duration", data.duration, true);
        fill(row, "unit_price", parseFloat(data.price) ? data.price : "", true);
        fill(row, "quantity", "1", false);
        recalcTreatment();
      });
    }
    treatmentTable.addEventListener("input", recalcTreatment);
    treatmentTable.addEventListener("change", recalcTreatment);
    recalcTreatment();
  }
})();

// Treatment templates: the chosen template is sent with the visit form, which is saved first.
(function () {
  "use strict";
  var select = document.querySelector("[data-template-select]");
  var button = document.querySelector("[data-template-apply]");
  if (!select || !button) return;
  select.addEventListener("change", function () {
    button.value = select.value;
    button.disabled = !select.value;
  });
})();
