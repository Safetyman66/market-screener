(function() {
  // 1. Detect directory context
  const isKnowledgeSubdir = window.location.pathname.toLowerCase().includes('/knowledge/') || 
                            window.location.pathname.toLowerCase().includes('\\knowledge\\');
  
  // From root: go into knowledge/. From knowledge/: stay in current folder.
  const toRoot = isKnowledgeSubdir ? '../' : './';
  const toKb = isKnowledgeSubdir ? './' : 'knowledge/';

  // 2. Navigation items
  const navItems = [
    { label: 'TOM Inflows', file: 'turn-of-the-month.html' },
    { label: 'Zacks Rank', file: 'zacks-rank-revisions.html' },
    { label: 'Index Inclusion', file: 'russell-reconstitution.html' },
    { label: 'OpEx Gamma', file: 'opex-gamma-dynamics.html' },
    { label: 'Binary Guardrails', file: 'macro-event-guardrails.html' },
    { label: 'Midterm Cycles', file: 'midterm-structural-cycles.html' },
    { label: 'Risk Protocols', file: 'execution-protocols-risk-governance.html' }
  ];

  // 3. Inject styling
  const style = document.createElement('style');
  style.textContent = `
    .corp-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem 1.5rem;
      background: var(--card-bg, #0f172a);
      border: 1px solid var(--border, #334155);
      border-radius: 8px;
      margin-bottom: 2rem;
      flex-wrap: wrap;
      gap: 1rem;
    }
    .corp-brand {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-weight: 800;
      font-size: 0.95rem;
      color: var(--text, #f8fafc);
      letter-spacing: 0.05em;
      white-space: nowrap;
    }
    .corp-nav {
      display: flex;
      gap: 0.5rem;
      font-size: 0.82rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .corp-nav a {
      color: var(--muted, #94a3b8);
      text-decoration: none;
      font-weight: 500;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      transition: all 0.2s ease;
    }
    .corp-nav a:hover {
      color: var(--accent, #38bdf8);
      background: rgba(56, 189, 248, 0.08);
    }
    .corp-nav a.active {
      color: var(--accent, #38bdf8);
      font-weight: 700;
      background: rgba(56, 189, 248, 0.14);
    }
    .corp-nav .divider {
      color: var(--border, #334155);
      user-select: none;
      margin: 0 0.2rem;
    }
    .corp-kb-label {
      color: var(--text, #f8fafc);
      font-weight: 600;
      margin-right: 0.2rem;
    }
  `;
  document.head.appendChild(style);

  // 4. Determine current active page
  const cleanPath = window.location.pathname.replace(/\\/g, '/');
  const currentPage = cleanPath.split('/').pop().toLowerCase() || 'intel.html';
  const isTerminal = currentPage === 'intel.html' || currentPage === 'index.html';

  let navLinksHtml = `
    <a href="${toRoot}intel.html" class="${isTerminal ? 'active' : ''}" style="${!isTerminal ? 'color: var(--accent, #38bdf8); font-weight: 600;' : ''}">
      ${isKnowledgeSubdir ? '← Screener Terminal' : 'Screener Terminal'}
    </a>
    <span class="divider">|</span>
    <span class="corp-kb-label">Knowledge Base:</span>
  `;

  navItems.forEach(item => {
    const isActive = currentPage === item.file.toLowerCase();
    navLinksHtml += `<a href="${toKb}${item.file}" class="${isActive ? 'active' : ''}">${item.label}</a>`;
  });

  const headerHtml = `
    <div class="corp-brand">
      <img src="${toRoot}logo.png" alt="Corp Acuity Logo" style="width: 22px; height: 22px; object-fit: contain;" />
      <span>CORP ACUITY // RESEARCH LAB</span>
    </div>
    <nav class="corp-nav">
      ${navLinksHtml}
    </nav>
  `;

  // 5. Mount the header
  const headerElem = document.createElement('header');
  headerElem.className = 'corp-header';
  headerElem.innerHTML = headerHtml;

  const target = document.querySelector('.container') || document.body.firstChild;
  if (target && target.parentNode) {
    target.parentNode.insertBefore(headerElem, target);
  } else {
    document.body.prepend(headerElem);
  }
})();