(function () {
  "use strict";

  var money = function (value) {
    return "Rs. " + value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  var number = function (input) {
    var value = parseFloat(input && input.value);
    return isNaN(value) ? 0 : value;
  };

  var form = document.querySelector("form[data-invoice-form]");
  if (form) {
    var discount = form.querySelector('input[name$="-discount"]');
    var vat = form.querySelector('input[name$="-vat_percent"]');

    // Line amounts and totals update as items are typed, so the bill can be read out before saving.
    var recalc = function () {
      // Lines from the visit are fixed on this page; only the other items are edited here.
      var subtotal = parseFloat(form.getAttribute("data-fixed-subtotal")) || 0;
      form.querySelectorAll("tr[data-invoice-line]").forEach(function (row) {
        var removed = row.querySelector('input[name$="-DELETE"]');
        var qty = number(row.querySelector('input[name$="-quantity"]'));
        var price = number(row.querySelector('input[name$="-unit_price"]'));
        var off = Math.min(Math.max(number(row.querySelector('input[name$="-discount_percent"]')), 0), 100);
        var amount = removed && removed.checked ? 0 : Math.round(qty * price * (100 - off)) / 100;
        subtotal += amount;
        var cell = row.querySelector("[data-line-total]");
        if (cell) cell.textContent = qty && price ? money(amount) : "";
      });
      var taxable = Math.max(subtotal - number(discount), 0);
      var vatAmount = Math.round(taxable * number(vat)) / 100;
      var total = taxable + vatAmount;
      form.querySelector("[data-subtotal]").textContent = money(subtotal);
      form.querySelector("[data-vat]").textContent = money(vatAmount);
      form.querySelector("[data-total]").textContent = money(total);
      var header = document.querySelector("[data-grand-total-display]");
      if (header) header.textContent = money(total);
    };

    form.addEventListener("input", recalc);
    form.addEventListener("change", recalc);

    // Choosing a product fills in its name and price; the price can still be changed.
    var onProductChosen = function (event) {
      var select = event.target;
      var data = event.params && event.params.data;
      var row = select.closest("tr[data-invoice-line]");
      if (!row || !data) return;
      var description = row.querySelector('input[name$="-description"]');
      var price = row.querySelector('input[name$="-unit_price"]');
      var qty = row.querySelector('input[name$="-quantity"]');
      if (description) description.value = data.name || description.value;
      if (price && data.price) price.value = data.price;
      if (qty && !qty.value) qty.value = "1";
      var hint = row.querySelector("[data-stock-hint]");
      if (hint) hint.textContent = data.stock !== "" && data.stock !== undefined ? parseFloat(data.stock) + " " + data.unit + " in stock here" : "";
      recalc();
      if (qty) qty.focus();
    };
    if (window.jQuery) jQuery(form).on("select2:select", "select", onProductChosen);

    recalc();
  }

  // Cancelling an issued invoice asks for a reason, which is kept with it.
  document.querySelectorAll("form[data-cancel-invoice]").forEach(function (cancel) {
    cancel.addEventListener("submit", function (event) {
      var reason = window.prompt("Cancel this invoice? Its items go back into stock. Reason (optional):", "");
      if (reason === null) {
        event.preventDefault();
        return;
      }
      cancel.querySelector('input[name="reason"]').value = reason;
    });
  });
})();
