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

  // Pulled from the illustrations, same as the CSS. Ordinal scales get the
  // single accent so the eye reads one shape; categorical answers get the
  // ink ramp, since their order carries no meaning to reinforce.
  var INK = "#0b0b0b";
  var MINT_DEEP = "#1f6f63";
  var CATEGORICAL_RAMP = [
    "#0b0b0b", "#1f6f63", "#3d3d3a", "#4a9d8f",
    "#6b6b66", "#7fc4b6", "#9b9b95", "#b8f2e6"
  ];

  function colorsFor(distribution) {
    if (distribution.type === "ordinal") {
      return MINT_DEEP;
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
          grid: { display: horizontal, color: "#e4e4de" },
          border: { display: false },
          ticks: { precision: 0, color: "#6b6b66" }
        },
        y: {
          beginAtZero: true,
          grid: { display: !horizontal, color: "#e4e4de" },
          border: { display: false },
          ticks: { precision: 0, color: "#6b6b66" }
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
          borderRadius: 4,
          maxBarThickness: 44
        }]
      },
      options: optionsFor(distribution)
    });
  });
})();
