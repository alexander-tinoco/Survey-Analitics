/* Marks which part of the record is being read.
 *
 * The four analysis pages this replaced left no sense of place; a record you
 * scroll through needs to say where you are in it. IntersectionObserver rather
 * than a scroll handler: the browser does the work off the main thread, and
 * there is nothing to throttle.
 */
(function () {
  "use strict";

  var links = Array.prototype.slice.call(document.querySelectorAll("[data-index-link]"));
  if (!links.length || !("IntersectionObserver" in window)) {
    return;
  }

  var byId = {};
  var sections = [];

  links.forEach(function (link) {
    var id = link.getAttribute("href").slice(1);
    var section = document.getElementById(id);
    if (section) {
      byId[id] = link;
      sections.push(section);
    }
  });

  function mark(id) {
    links.forEach(function (link) {
      link.removeAttribute("aria-current");
    });
    if (byId[id]) {
      byId[id].setAttribute("aria-current", "true");
    }
  }

  var observer = new IntersectionObserver(
    function (entries) {
      // The topmost intersecting section wins, so scrolling up marks the
      // section being entered rather than the one being left.
      var visible = entries
        .filter(function (entry) { return entry.isIntersecting; })
        .sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; });

      if (visible.length) {
        mark(visible[0].target.id);
      }
    },
    // Top band only: a section counts as "being read" once its heading has
    // reached the upper third, not when its last paragraph is still on screen.
    { rootMargin: "-72px 0px -66% 0px", threshold: 0 }
  );

  sections.forEach(function (section) {
    observer.observe(section);
  });

  mark(sections[0].id);
})();
