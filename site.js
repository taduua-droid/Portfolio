/* Menu, footer fade-in and the footer clock. The site still works with this file missing. */
(function () {
  var d = document, body = d.body;
  var btn = d.querySelector('.menu-btn'), menu = d.getElementById('menu'), backdrop = d.querySelector('.menu-backdrop');

  function setMenu(open, returnFocus) {
    body.classList.toggle('menu-open', open);
    btn.setAttribute('aria-expanded', String(open));
    btn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    d.querySelectorAll('main, .banner, .next, .site-footer').forEach(function (el) { el.inert = open; });
    if (open) { var first = menu.querySelector('a'); if (first) first.focus({ preventScroll: true }); }
    else if (returnFocus) btn.focus({ preventScroll: true });
  }
  if (btn && menu) {
    btn.addEventListener('click', function () { setMenu(!body.classList.contains('menu-open'), true); });
    backdrop.addEventListener('click', function () { setMenu(false, true); });
    menu.addEventListener('click', function (e) { if (e.target.closest('a')) setMenu(false, false); });
    d.addEventListener('keydown', function (e) { if (e.key === 'Escape' && body.classList.contains('menu-open')) setMenu(false, true); });
  }

  var items = d.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
    }, { threshold: 0.08 });
    items.forEach(function (el) { io.observe(el); });
  } else { items.forEach(function (el) { el.classList.add('in'); }); }

  var clock = d.getElementById('clock');
  if (clock) {
    try {
      var fmt = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' });
      (function tick() { clock.textContent = 'New York, ' + fmt.format(new Date()); setTimeout(tick, 15000); })();
    } catch (e) { /* leave the plain location text */ }
  }
})();
