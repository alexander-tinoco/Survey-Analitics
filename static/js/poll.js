/* Polls for a background analysis result and reloads when it lands.
 *
 * Deliberately small: the server renders the finished page, so this only has
 * to notice when there is one. A client-side renderer would duplicate the
 * template and let the two drift apart.
 */
(function () {
  "use strict";

  var panel = document.querySelector("[data-poll-url]");
  if (!panel) {
    return;
  }

  var url = panel.getAttribute("data-poll-url");
  var status = panel.querySelector('[role="status"]');

  // Backs off from 2s toward 15s. A job that takes a minute should not be
  // asked thirty times, and one that finishes fast is still caught quickly.
  var delay = 2000;
  var MAX_DELAY = 15000;
  var GIVE_UP_AFTER = 5 * 60 * 1000;
  var startedAt = Date.now();

  function stop(message) {
    if (status) {
      status.textContent = message;
    }
  }

  function poll() {
    if (Date.now() - startedAt > GIVE_UP_AFTER) {
      stop("This is taking longer than expected. Reload to check again.");
      return;
    }

    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (response) {
        // 200 means the representation exists; 202 means still working.
        if (response.status === 200) {
          window.location.reload();
          return;
        }
        schedule();
      })
      .catch(function () {
        // A dropped request is not a failed job — keep waiting.
        schedule();
      });
  }

  function schedule() {
    delay = Math.min(delay * 1.5, MAX_DELAY);
    window.setTimeout(poll, delay);
  }

  window.setTimeout(poll, delay);
})();
