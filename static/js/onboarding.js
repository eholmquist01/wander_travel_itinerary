// Onboarding and trip vibe pages.
// Without JavaScript, every question shows on one page and the forms still work.

(function () {
  // Live "x of max chosen" counter that blocks choosing more than the max
  function limitChoices(form, selector, max, counter) {
    var inputs = Array.prototype.slice.call(form.querySelectorAll(selector));
    if (!inputs.length || !counter) return;

    function update() {
      var chosen = inputs.filter(function (i) { return i.checked; }).length;
      counter.textContent = chosen;
      inputs.forEach(function (i) {
        var full = chosen >= max && !i.checked;
        i.disabled = full;
        i.closest("label").classList.toggle("is-disabled", full);
      });
    }

    // Listen to every input in the form so switching away from a choice also updates the count
    form.addEventListener("change", update);
    update();
  }

  // ---------- Onboarding: one question per screen ----------
  var form = document.getElementById("onboarding");
  if (form) {
    limitChoices(form, 'input[name^="interest_"][value="like"]',
                 parseInt(form.dataset.maxLikes, 10) || 4,
                 form.querySelector("[data-like-count]"));

    var steps = Array.prototype.slice.call(form.querySelectorAll(".ob-step"));
    var nav = form.querySelector(".ob-nav");
    var back = nav.querySelector("[data-back]");
    var next = nav.querySelector("[data-next]");
    var progress = form.querySelector(".ob-progress");
    var bar = form.querySelector(".ob-progress-bar");
    var label = form.querySelector("[data-progress-label]");
    var count = form.querySelector("[data-progress-count]");
    var current = 0;

    // After a validation error, the server tells us which step to reopen
    if (form.dataset.start) {
      var start = steps.findIndex(function (s) { return s.id === form.dataset.start; });
      if (start >= 0) current = start;
    }

    form.classList.add("is-stepper");
    progress.hidden = false;
    nav.hidden = false;

    function show(index, scroll) {
      current = Math.max(0, Math.min(index, steps.length - 1));
      steps.forEach(function (s, k) { s.classList.toggle("is-active", k === current); });
      back.style.visibility = current === 0 ? "hidden" : "visible";
      next.hidden = current === steps.length - 1;
      bar.style.width = ((current + 1) / steps.length * 100) + "%";
      label.textContent = steps[current].dataset.label;
      count.textContent = "Step " + (current + 1) + " of " + steps.length;
      if (scroll) {
        window.scrollTo({ top: form.getBoundingClientRect().top + window.scrollY - 16, behavior: "smooth" });
      }
    }

    back.addEventListener("click", function () { show(current - 1, true); });
    next.addEventListener("click", function () { show(current + 1, true); });

    // Picking an answer on a this-or-that question moves to the next one
    form.querySelectorAll(".ob-pair-step input[type=radio]").forEach(function (input) {
      input.addEventListener("change", function () {
        setTimeout(function () { show(current + 1, false); }, 280);
      });
    });

    show(current, false);
  }

  // ---------- Trip vibe: focus limit ----------
  var vibeForm = document.getElementById("trip-vibe");
  if (vibeForm) {
    limitChoices(vibeForm, 'input[name="focus"]',
                 parseInt(vibeForm.dataset.maxFocus, 10) || 3,
                 vibeForm.querySelector("[data-focus-count]"));
  }
})();