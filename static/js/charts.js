/* Renders the distribution charts on the descriptive dashboard.
 *
 * Data is read from a json_script block already in the page rather than
 * fetched: the server computed it to render the tables, so a second request
 * would only add latency and a spinner.
 *
 * Every chart here has a table beside it carrying the same numbers. The chart
 * is for shape, the table is for values — and for screen readers, to which a
 * canvas is opaque.
 */
(function () {
  "use strict";

  var payload = document.getElementById("chart-data");
  if (!payload || typeof Chart === "undefined") {
    // Without Chart.js the tables still carry every number, so the page
    // degrades to something readable instead of something broken.
    return;
  }

  var summary = JSON.parse(payload.textContent);

  // The record's own ink, read from the stylesheet so a palette change in one
  // place cannot leave the charts behind.
  var styles = getComputedStyle(document.documentElement);
  function token(name, fallback) {
    return (styles.getPropertyValue(name) || "").trim() || fallback;
  }

  var INK = token("--ink", "#0b0f0e");
  var RULE = token("--rule", "#d5ddd7");
  var MUTED = token("--ink-soft", "#4a5551");

  // An ordinal scale is one measurement along one axis, so its bars share a
  // single ink and the shape carries the meaning. Categorical answers have no
  // order to reinforce, so they step down a ramp instead.
  var ORDINAL_INK = token("--stamp", "#1f6f63");
  var CATEGORICAL_RAMP = [
    "#0b0f0e", "#1f6f63", "#3c4a45", "#4a9d8f",
    "#6b7671", "#7fc4b6", "#98a29d", "#b8f2e6"
  ];

  function colorsFor(distribution) {
    if (distribution.type === "ordinal") {
      return ORDINAL_INK;
    }
    return distribution.counts.map(function (_, index) {
      return CATEGORICAL_RAMP[index % CATEGORICAL_RAMP.length];
    });
  }

  function optionsFor(distribution) {
    // Ordinal answers run along the x axis to preserve their scale order,
    // which is the whole point of the ordering; categorical answers run
    // horizontally so long option labels stay readable.
    var horizontal = distribution.type !== "ordinal";

    return {
      indexAxis: horizontal ? "y" : "x",
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: INK,
          padding: 10,
          titleFont: { family: "Archivo, sans-serif" },
          bodyFont: { family: "Roboto Mono, monospace" },
          displayColors: false,
          callbacks: {
            label: function (item) {
              var entry = distribution.counts[item.dataIndex];
              return entry.count + " respondents (" + entry.percentage + "%)";
            }
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { display: horizontal, color: RULE },
          border: { display: false },
          ticks: { precision: 0, color: MUTED, font: { family: "Roboto Mono, monospace", size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { display: !horizontal, color: RULE },
          border: { display: false },
          ticks: { precision: 0, color: MUTED, font: { family: "Roboto Mono, monospace", size: 11 } }
        }
      }
    };
  }

  summary.distributions.forEach(function (distribution) {
    if (!distribution.counts.length) {
      return;
    }

    var canvas = document.querySelector('[data-chart="' + distribution.position + '"]');
    if (!canvas) {
      return;
    }

    new Chart(canvas, {
      type: "bar",
      data: {
        labels: distribution.counts.map(function (c) { return c.value; }),
        datasets: [{
          data: distribution.counts.map(function (c) { return c.count; }),
          backgroundColor: colorsFor(distribution),
          borderRadius: 1,
          maxBarThickness: 44
        }]
      },
      options: optionsFor(distribution)
    });
  });
})();
