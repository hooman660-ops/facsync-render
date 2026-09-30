(() => {
  'use strict';
  const config = document.getElementById('admin-navigation-destinations');
  const main = document.querySelector('main.main-content');
  if (!config || !main) return;
  const destinations = JSON.parse(config.textContent);
  let placeholder = null;
  let recoveryTimer;
  let scrollPosition;
  let navigationState = [];

  const block = (kind = '') => `<div class="admin-skeleton-block ${kind}"></div>`;
  const panel = (content) => `<div class="admin-skeleton-panel">${content}</div>`;
  const cards = (count) => `<div class="admin-skeleton-grid">${Array.from({ length: count }, () => panel(block('admin-skeleton-short') + block('admin-skeleton-value') + block())).join('')}</div>`;
  const charts = () => `<div class="admin-skeleton-grid admin-skeleton-charts">${Array.from({ length: 2 }, () => panel(block('admin-skeleton-short') + block('admin-skeleton-chart'))).join('')}</div>`;

  function restore() {
    clearTimeout(recoveryTimer);
    if (!placeholder) return;
    placeholder.remove();
    placeholder = null;
    main.classList.remove('admin-navigation-hidden');
    navigationState.forEach(([link, active]) => {
      link.classList[active ? 'add' : 'remove']('active');
    });
    navigationState = [];
    window.scrollTo(scrollPosition.x, scrollPosition.y);
  }

  function show([title, layout], destinationUrl) {
    restore();
    navigationState = Array.from(document.querySelectorAll('.sidebar .nav-item'), link => [link, link.classList.contains('active')]);
    navigationState.forEach(([link]) => {
      const url = new URL(link.href, window.location.href);
      const selected = url.pathname === destinationUrl.pathname && url.search === destinationUrl.search;
      link.classList[selected ? 'add' : 'remove']('active');
    });
    scrollPosition = { x: window.scrollX, y: window.scrollY };
    placeholder = document.createElement('main');
    placeholder.className = 'main-content admin-navigation-loading';
    const heading = document.createElement('h1');
    heading.textContent = title;
    const status = document.createElement('p');
    status.className = 'admin-navigation-status';
    status.setAttribute('role', 'status');
    status.textContent = `Loading ${title}…`;
    const shapes = document.createElement('div');
    shapes.setAttribute('aria-hidden', 'true');
    if (layout === 'table') {
      shapes.innerHTML = panel(block('admin-skeleton-short') + Array.from({ length: 7 }, () => block('admin-skeleton-row')).join(''));
    } else if (layout === 'form') {
      shapes.className = 'admin-skeleton-form';
      shapes.innerHTML = panel(Array.from({ length: 4 }, () => block('admin-skeleton-short') + block('admin-skeleton-field')).join(''));
    } else {
      shapes.innerHTML = cards(layout === 'cards' ? 6 : 3) + (layout === 'cards' ? '' : charts());
    }
    placeholder.append(heading, status, shapes);
    main.classList.add('admin-navigation-hidden');
    main.after(placeholder);
    window.scrollTo(0, 0);
    // A stopped request or a download must not leave the current page hidden.
    recoveryTimer = window.setTimeout(restore, 12000);
  }

  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a');
    if (!link || !link.closest('.sidebar') || link.hasAttribute('download')) return;
    const target = link.getAttribute('target') || document.querySelector('base')?.target;
    if (target && target.toLowerCase() !== '_self') return;
    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin || url.hash || (!placeholder && link.classList.contains('active'))) return;
    if (url.pathname === window.location.pathname && url.search === window.location.search) return;
    const destination = destinations[url.pathname];
    if (!destination) return;
    // Keep ordinary browser navigation, including cancellation by other handlers.
    queueMicrotask(() => { if (!event.defaultPrevented) show(destination, url); });
  });
  window.addEventListener('pageshow', restore);
  window.addEventListener('pagehide', restore);
  window.addEventListener('popstate', restore);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') restore(); });
})();
