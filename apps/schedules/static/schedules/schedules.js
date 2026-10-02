(function () {
  "use strict";

  // Weekly hours: copy Monday to the other weekdays, or clear a day.
  var hours = document.querySelector("form[data-weekly-hours]");
  if (hours) {
    var rows = Array.prototype.slice.call(hours.querySelectorAll("tr[data-weekday-row]"));
    var inputs = function (row) { return row.querySelectorAll('input[type="time"]'); };

    hours.addEventListener("click", function (event) {
      var copy = event.target.closest("[data-copy-weekdays]");
      var clear = event.target.closest("[data-clear-day]");
      if (copy) {
        var monday = inputs(rows[0]);
        rows.slice(1, 5).forEach(function (row) {
          inputs(row).forEach(function (input, index) { input.value = monday[index].value; });
        });
      } else if (clear) {
        inputs(clear.closest("tr")).forEach(function (input) { input.value = ""; });
      }
    });
  }

  // Leave or extra shift: only an extra shift has a branch.
  var kind = document.querySelector('select[name="kind"]');
  var branch = document.querySelector('select[name="branch"]');
  if (kind && branch) {
    var branchRow = branch.closest(".row");
    var applyKind = function () {
      if (branchRow) branchRow.classList.toggle("d-none", kind.value === "leave");
    };
    kind.addEventListener("change", applyKind);
    applyKind();
  }

  // Walk-in or booking: show who works on the chosen date, next to "Attended by".
  var visit = document.querySelector("form[data-availability-url]");
  if (visit) {
    var url = visit.getAttribute("data-availability-url");
    var date = visit.querySelector('input[name="visit_date"]');
    var doctor = visit.querySelector('select[name="attended_by"]');
    if (!date || !doctor) return;

    var hint = document.createElement("div");
    hint.className = "form-text";
    hint.setAttribute("data-roster-hint", "");
    hint.setAttribute("aria-live", "polite");
    var holder = doctor.closest(".fv-row") || doctor.parentNode;
    holder.appendChild(hint);

    // Option labels are "Name · designation — status"; keep the part before the status.
    var SEPARATOR = " — ";
    Array.prototype.forEach.call(doctor.options, function (option) {
      option.setAttribute("data-name", option.text.split(SEPARATOR)[0]);
    });

    var escape = function (text) {
      var span = document.createElement("span");
      span.textContent = text;
      return span.innerHTML;
    };

    var update = function () {
      if (!date.value) return;
      fetch(url + "?date=" + encodeURIComponent(date.value), { credentials: "same-origin" })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (data) {
          if (!data) return;
          var byId = {};
          data.doctors.forEach(function (row) { byId[String(row.id)] = row; });
          Array.prototype.forEach.call(doctor.options, function (option) {
            if (!option.value) return;
            var row = byId[option.value];
            var name = option.getAttribute("data-name");
            option.text = row && row.summary ? name + SEPARATOR + row.summary : name;
          });
          if (window.jQuery) jQuery(doctor).trigger("change.select2");

          if (!data.doctors.length) {
            hint.innerHTML = "";
            return;
          }
          hint.innerHTML = "<span class=\"text-gray-600\">Doctors " + escape(data.label) + ":</span> " +
            data.doctors.map(function (row) {
              return "<span class=\"text-nowrap me-2\"><span class=\"bullet bullet-dot bg-" + escape(row.color) +
                " h-8px w-8px me-1\"></span>" + escape(row.name) + " <span class=\"text-muted\">" +
                escape(row.status + (row.detail ? " " + row.detail : "")) + "</span></span>";
            }).join(" ");
        })
        .catch(function () {});
    };

    date.addEventListener("change", update);
    update();
  }
})();
