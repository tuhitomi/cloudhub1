import {htmlText} from './i18n.js';
import {t as tr} from './i18n.js';
/**
 * CloudHub Shell View Component (Vanilla ES Module)
 * Conforms to SHELL-CONTRACT.md
 *
 * Renders:
 * 1. Portal Navigation Bar (#portal-nav): Section anchors with SVG icons & onNavigate callback
 * 2. Overview & Cost Snapshot (#overview-snapshot): Compact status metrics & cost coverage
 */

/**
 * Returns an inline SVG icon string for a navigation section ID.
 * @param {string} id
 * @returns {string}
 */
function getNavIconSvg(id) {
  switch (id) {
    case 'overview-snapshot': return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 10L12 3l9 7v10H3z M9 20v-7h6v7"/></svg>`;
    case 'catalog-section':
      // Template / Grid icon
      return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
        <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
        <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
        <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
      </svg>`;
    case 'environments-section':
      // Server / Layers icon
      return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
        <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
        <line x1="6" y1="6" x2="6.01" y2="6"></line>
        <line x1="6" y1="18" x2="6.01" y2="18"></line>
      </svg>`;
    case 'backups-section':
      // Database / Archive icon
      return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
        <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
      </svg>`;
    case 'operations-section':
      // Activity / Pulse icon
      return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
      </svg>`;
    case 'history-section':
      // Clock / History icon
      return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10"></circle>
        <polyline points="12 6 12 12 16 14"></polyline>
      </svg>`;
    case 'admin':
      // Shield / Settings icon
      return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
      </svg>`;
    default:
      return `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="3"></circle>
      </svg>`;
  }
}

/**
 * Creates and mounts the CloudHub portal navigation and overview snapshot view.
 *
 * @param {Object} callbacks
 * @param {Function} [callbacks.onNavigate] - Callback invoked with section ID (e.g. 'catalog-section')
 * @param {Function} [callbacks.onRefresh] - Callback invoked when user clicks refresh
 * @returns {{ update: (props: Object) => void }}
 */
export function createShellView(callbacks = {}) {
  const navHost = document.querySelector('#portal-nav');
  const overviewHost = document.querySelector('#overview-snapshot');

  // If hosts are absent, return a safe no-op updater
  if (!navHost && !overviewHost) {
    return {
      update() {}
    };
  }

  // --- 1. Mount Portal Navigation in navHost ---
  let navListEl = null;
  if (navHost) {
    navHost.innerHTML = `
      <nav class="portal-nav-bar" aria-label="${htmlText("ui.81c27c42e01b")}">
        <ul class="portal-nav-list"></ul>
      </nav>
    `;
    navListEl = navHost.querySelector('.portal-nav-list');
  }

  // --- 2. Mount Overview Snapshot in overviewHost ---
  let overviewTitleEl = null;
  let overviewUpdatedEl = null;
  let refreshBtn = null;
  let refreshTextEl = null;
  let noticeBanner = null;
  let errorBanner = null;
  let authBanner = null;
  let metricsGrid = null;
  let estimateValEl = null;
  let actualValEl = null;
  let coverageValEl = null;

  if (overviewHost) {
    overviewHost.innerHTML = `
      <section class="overview-snapshot-container" aria-labelledby="overview-heading">
        <div class="overview-card">
          <div class="overview-card-header">
            <div class="overview-heading-group">
              <h2 id="overview-heading" class="overview-heading">${htmlText("ui.4780073d43d6")}</h2>
              <span class="overview-updated-badge" role="status" aria-live="polite"></span>
            </div>
            <div class="overview-actions">
              <button type="button" id="overview-refresh-btn" class="btn btn-secondary overview-refresh-btn">
                <span class="refresh-spinner" aria-hidden="true" hidden></span>
                <span class="refresh-label">${htmlText("ui.b4c61340c8f4")}</span>
              </button>
            </div>
          </div>

          <div class="overview-notice-banner" role="status" aria-live="polite" hidden></div>
          <div class="overview-error-banner" role="alert" hidden></div>
          <div class="overview-auth-banner" role="note" hidden></div>

          <div class="overview-card-body">
            <!-- Compact Metrics Grid -->
            <div class="overview-metrics-grid" role="region" aria-label="${htmlText("ui.f64224ca93d2")}"></div>

            <!-- Cost & Coverage Breakdown Strip -->
            <div class="overview-cost-strip" role="region" aria-label="${htmlText("ui.29b503d31f18")}">
              <div class="cost-stat-item">
                <span class="cost-stat-label">${htmlText("ui.c660de6cb732")}</span>
                <strong class="cost-stat-value estimate-value">--</strong>
                <small class="cost-stat-hint">${htmlText("ui.4683ad15bcf8")}</small>
              </div>
              <div class="cost-stat-item">
                <span class="cost-stat-label">${htmlText("ui.f6722d422c93")}</span>
                <strong class="cost-stat-value actual-value">--</strong>
                <small class="cost-stat-hint">${htmlText("ui.9076e9269488")}</small>
              </div>
              <div class="cost-stat-item cost-stat-coverage">
                <span class="cost-stat-label">${htmlText("ui.7ec8fe09a289")}</span>
                <details class="coverage-details"><summary>${htmlText("workspace.coverage")}</summary><span class="cost-stat-value coverage-value">--</span></details>
                <small class="cost-stat-hint">${htmlText("ui.c310cecb42cc")}</small>
              </div>
            </div>

            <p class="overview-cost-disclaimer">
              ${htmlText("ui.69ff74e8b185")}
            </p>
          </div>
        </div>
      </section>
    `;

    overviewTitleEl = overviewHost.querySelector('#overview-heading');
    overviewUpdatedEl = overviewHost.querySelector('.overview-updated-badge');
    refreshBtn = overviewHost.querySelector('#overview-refresh-btn');
    refreshTextEl = overviewHost.querySelector('.refresh-label');
    noticeBanner = overviewHost.querySelector('.overview-notice-banner');
    errorBanner = overviewHost.querySelector('.overview-error-banner');
    authBanner = overviewHost.querySelector('.overview-auth-banner');
    metricsGrid = overviewHost.querySelector('.overview-metrics-grid');
    estimateValEl = overviewHost.querySelector('.estimate-value');
    actualValEl = overviewHost.querySelector('.actual-value');
    coverageValEl = overviewHost.querySelector('.coverage-value');

    // Bind refresh listener ONCE
    refreshBtn.addEventListener('click', () => {
      callbacks.onRefresh?.();
    });
  }

  // Cache to track and avoid unnecessary DOM re-creations
  let lastNavItemsKey = '';
  let lastStatsKey = null;
  let activeNavId = '';

  /**
   * Helper to update textContent only if modified.
   */
  function setTextIfChanged(el, text) {
    if (!el) return;
    const str = text == null ? '' : String(text);
    if (el.textContent !== str) {
      el.textContent = str;
    }
  }

  /**
   * Update active nav link highlighting
   */
  function setActiveNav(id) {
    activeNavId = id;
    if (!navListEl) return;
    const links = navListEl.querySelectorAll('.portal-nav-link');
    links.forEach((a) => {
      const href = a.getAttribute('href') || '';
      if (href === `#${id}`) {
        a.classList.add('is-active');
        a.setAttribute('aria-current', 'location');
      } else {
        a.classList.remove('is-active');
        a.removeAttribute('aria-current');
      }
    });
  }

  /**
   * Update shell view presentation with incoming props.
   *
   * @param {Object} props
   */
  function update(props = {}) {
    const authenticated = Boolean(props.authenticated);
    const isAdmin = Boolean(props.admin);
    const loading = Boolean(props.loading);
    const error = props.error ? String(props.error) : '';
    const lastUpdatedText = props.lastUpdatedText ? String(props.lastUpdatedText) : '';
    const stats = Array.isArray(props.stats) ? props.stats : [];
    const estimateText = props.estimateText ? String(props.estimateText) : '--';
    const actualCostText = props.actualCostText ? String(props.actualCostText) : '--';
    const coverageText = props.coverageText ? String(props.coverageText) : '--';
    const rawNavItems = Array.isArray(props.navItems) ? props.navItems : [];

    // --- A. Update Navigation Links (Filter admin when admin=false; rebuild only if changed) ---
    if (navListEl) {
      // Gate admin section link if admin is false
      const filteredNavItems = rawNavItems.filter((item) => {
        if (item && item.id === 'admin' && !isAdmin) {
          return false;
        }
        return true;
      });

      const currentNavKey = filteredNavItems.map((item) => `${item.id}:${item.label}`).join('|');
      if (currentNavKey !== lastNavItemsKey) {
        lastNavItemsKey = currentNavKey;
        navListEl.replaceChildren();

        for (const item of filteredNavItems) {
          const li = document.createElement('li');
          li.className = 'portal-nav-item';

          const a = document.createElement('a');
          a.className = 'portal-nav-link';
          a.href = `#${item.id}`;

          // SVG Icon + Label
          a.innerHTML = getNavIconSvg(item.id); // Trusted, static SVG only.
          const label = document.createElement('span');
          label.className = 'nav-label';
          label.textContent = item.label || item.id;
          a.append(label);

          if (item.id === activeNavId) {
            a.classList.add('is-active');
            a.setAttribute('aria-current', 'location');
          }

          a.addEventListener('click', (e) => {
            e.preventDefault();
            setActiveNav(item.id);
            callbacks.onNavigate?.(item.id);
          });

          li.appendChild(a);
          navListEl.appendChild(li);
        }
      }
      const requestedId = props.activeSection ?? activeNavId;
      setActiveNav(filteredNavItems.some(item => item.id === requestedId) ? requestedId : '');
    }

    // --- B. Update Overview Snapshot ---
    if (overviewHost) {
      // 1. Updated Timestamp (Prefix with "Cập nhật: " for bare timestamp)
      if (lastUpdatedText) {
        overviewUpdatedEl.hidden = false;
        setTextIfChanged(overviewUpdatedEl, tr("ui.0f839f2adba9",{p0:(lastUpdatedText)}));
      } else {
        overviewUpdatedEl.hidden = true;
        setTextIfChanged(overviewUpdatedEl, '');
      }

      // 2. Refresh Button State
      const spinnerEl = refreshBtn ? refreshBtn.querySelector('.refresh-spinner') : null;
      if (refreshBtn) {
        refreshBtn.disabled = loading || !authenticated;
        if (loading) {
          if (spinnerEl) spinnerEl.hidden = false;
          setTextIfChanged(refreshTextEl, tr("ui.449b88369113"));
        } else {
          if (spinnerEl) spinnerEl.hidden = true;
          setTextIfChanged(refreshTextEl, tr("ui.b4c61340c8f4"));
        }
      }

      // 3. Auth Guidance Banner
      if (!authenticated) {
        authBanner.hidden = false;
        setTextIfChanged(
          authBanner,
          tr("ui.221b9876620a")
        );
      } else {
        authBanner.hidden = true;
        setTextIfChanged(authBanner, '');
      }

      // 4. Loading Notice
      if (loading && authenticated) {
        noticeBanner.hidden = false;
        setTextIfChanged(noticeBanner, tr("ui.839bd0327e74"));
      } else {
        noticeBanner.hidden = true;
        setTextIfChanged(noticeBanner, '');
      }

      // 5. Error Banner (Verbatim error message with instruction to click "Làm mới")
      if (error && authenticated) {
        errorBanner.hidden = false;
        setTextIfChanged(
          errorBanner,
          tr("ui.3ad60f609851",{p0:(error)})
        );
      } else {
        errorBanner.hidden = true;
        setTextIfChanged(errorBanner, '');
      }

      // 6. Metrics Grid (Do not guess 0 when stats are empty or missing; show 'Chưa tải dữ liệu' or '--')
      const currentStatsKey = JSON.stringify([authenticated, stats]);
      if (currentStatsKey !== lastStatsKey) {
        lastStatsKey = currentStatsKey;
        metricsGrid.replaceChildren();

        if (stats.length === 0) {
          const emptyChip = document.createElement('div');
          emptyChip.className = 'metric-chip metric-chip-muted';

          const lbl = document.createElement('span');
          lbl.className = 'metric-label';
          lbl.textContent = tr("ui.cb31de8160c9");

          const val = document.createElement('strong');
          val.className = 'metric-value';
          val.textContent = authenticated ? tr("ui.b6858ba2e3b7") : '--';

          emptyChip.append(lbl, val);
          metricsGrid.appendChild(emptyChip);
        } else {
          for (const stat of stats) {
            const chip = document.createElement('div');
            chip.className = 'metric-chip';

            // Subtle semantic accent based on stat labels
            const lowerLabel = (stat.label || '').toLowerCase();
            if (lowerLabel.includes(tr("ui.9f2be3acefea")) || lowerLabel.includes(tr("ui.403114c3aec6")) || lowerLabel.includes(tr("ui.31589cadf603")) || lowerLabel.includes(tr("ui.a0f800725577"))) {
              chip.classList.add('metric-chip-danger');
            } else if (lowerLabel.includes(tr("ui.711af7c77a27")) || lowerLabel.includes('ready')) {
              chip.classList.add('metric-chip-success');
            } else if (lowerLabel.includes(tr("ui.4312e20baeac")) || lowerLabel.includes(tr("ui.8216bf8f4955")) || lowerLabel.includes(tr("ui.8cc28d7bb429"))) {
              chip.classList.add('metric-chip-info');
            } else if (lowerLabel.includes(tr("ui.083bf76d2307")) || lowerLabel.includes(tr("ui.4efd8f86b37f")) || lowerLabel.includes(tr("ui.eea0842fc4d5"))) {
              chip.classList.add('metric-chip-warning');
            }

            const lbl = document.createElement('span');
            lbl.className = 'metric-label';
            lbl.textContent = stat.label || '';

            const val = document.createElement('strong');
            val.className = 'metric-value';
            val.textContent = Number.isInteger(stat.count) ? String(stat.count) : (stat.value != null && stat.value !== '') ? String(stat.value) : '--';

            chip.append(lbl, val);
            metricsGrid.appendChild(chip);
          }
        }
      }

      // 7. Cost Breakdown Values (Separate labels, no self-computed totals)
      setTextIfChanged(estimateValEl, estimateText);
      setTextIfChanged(actualValEl, actualCostText);
      setTextIfChanged(coverageValEl, coverageText);
    }
  }

  return { update };
}
