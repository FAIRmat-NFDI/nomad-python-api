(() => {
  const template = document.getElementById("nomad-guide-switcher-template");
  const source = document.querySelector(".md-header__inner > .md-header__source");
  if (!template || !source) return;

  const selector = template.content.firstElementChild.cloneNode(true);
  source.before(selector);

  document.addEventListener("click", (event) => {
    if (!selector.contains(event.target)) selector.open = false;
  });

  selector.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && selector.open) {
      selector.open = false;
      selector.querySelector("summary").focus();
    }
  });
})();
