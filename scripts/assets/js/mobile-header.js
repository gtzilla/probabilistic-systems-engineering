(function () {
  function initMobileHeader(header) {
    var toggle = header.querySelector('[data-mobile-menu-toggle]');
    var menu = header.querySelector('[data-mobile-menu]');
    if (!toggle || !menu) return;

    var mq = window.matchMedia('(max-width: 900px)');
    var ticking = false;
    var lastY = window.scrollY || 0;

    function setMenu(open) {
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      menu.setAttribute('aria-hidden', open ? 'false' : 'true');
      document.body.classList.toggle('mobile-menu-open', open);
      if (open) {
        document.body.classList.remove('mobile-header-hidden');
        document.body.classList.add('mobile-header-compact');
      }
      updateOffset();
    }

    function updateOffset() {
      if (!mq.matches) {
        document.body.style.removeProperty('--mobile-header-offset');
        return;
      }
      window.requestAnimationFrame(function () {
        document.body.style.setProperty('--mobile-header-offset', header.offsetHeight + 'px');
      });
    }

    function applyScrollState() {
      if (!mq.matches) {
        document.body.classList.remove('mobile-header-compact', 'mobile-header-hidden', 'mobile-menu-open');
        toggle.setAttribute('aria-expanded', 'false');
        menu.setAttribute('aria-hidden', 'true');
        updateOffset();
        lastY = window.scrollY || 0;
        return;
      }

      var y = window.scrollY || 0;
      var menuOpen = toggle.getAttribute('aria-expanded') === 'true';

      if (menuOpen) {
        document.body.classList.remove('mobile-header-hidden');
        document.body.classList.add('mobile-header-compact');
        updateOffset();
        lastY = y;
        return;
      }

      if (y < 24) {
        document.body.classList.remove('mobile-header-compact', 'mobile-header-hidden');
      } else if (y < 88) {
        document.body.classList.add('mobile-header-compact');
        document.body.classList.remove('mobile-header-hidden');
      } else if (y > lastY + 8) {
        document.body.classList.add('mobile-header-hidden', 'mobile-header-compact');
      } else if (y < lastY - 8) {
        document.body.classList.remove('mobile-header-hidden');
        document.body.classList.add('mobile-header-compact');
      }

      lastY = y;
      updateOffset();
    }

    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') !== 'true';
      setMenu(open);
    });

    document.addEventListener('click', function (event) {
      if (!mq.matches) return;
      if (toggle.getAttribute('aria-expanded') !== 'true') return;
      if (header.contains(event.target)) return;
      setMenu(false);
    });

    window.addEventListener('scroll', function () {
      if (!mq.matches) return;
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () {
        applyScrollState();
        ticking = false;
      });
    }, { passive: true });

    window.addEventListener('resize', applyScrollState);
    window.addEventListener('orientationchange', applyScrollState);

    applyScrollState();
  }

  document.addEventListener('DOMContentLoaded', function () {
    var header = document.querySelector('[data-mobile-header]');
    if (!header) return;
    initMobileHeader(header);
  });
})();
