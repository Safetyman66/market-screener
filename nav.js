// Corp Acuity // Global Dynamic Header Navigation Engine
(function() {
  const currentPath = window.location.pathname;

  const navHtml = `
    <header style="
      background: #090d16;
      border-bottom: 1px solid #1e293b;
      padding: 0.85rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
      position: sticky;
      top: 0;
      z-index: 1000;
    ">
      <div style="display: flex; align-items: center; gap: 0.75rem;">
        <a href="/" style="text-decoration: none; display: flex; align-items: center; gap: 0.6rem;">
          <img src="/logo.png" alt="Corp Acuity Logo" style="height: 28px; width: auto; border-radius: 4px;" onerror="this.style.display='none'">
          <span style="font-weight: 800; font-size: 1.05rem; letter-spacing: 0.05em; color: #f8fafc;">
            CORP ACUITY <span style="color: #38bdf8;">//</span> RESEARCH LAB
          </span>
        </a>
      </div>

      <nav style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
        <!-- Core App Navigation -->
        <a href="/" style="
          color: ${currentPath === '/' || currentPath.endsWith('/index.html') ? '#38bdf8' : '#94a3b8'};
          text-decoration: none;
          font-size: 0.84rem;
          font-weight: 600;
          padding: 0.35rem 0.65rem;
          border-radius: 4px;
        ">Deck Carousel</a>

        <a href="/intel.html" style="
          color: ${currentPath.includes('intel.html') ? '#070a12' : '#f8fafc'};
          background: ${currentPath.includes('intel.html') ? '#38bdf8' : '#1e293b'};
          text-decoration: none;
          font-size: 0.84rem;
          font-weight: 700;
          padding: 0.35rem 0.75rem;
          border-radius: 5px;
          border: 1px solid #334155;
        ">Screener Terminal</a>

        <a href="/daily_market_intelligence.pdf" target="_blank" style="
          color: #94a3b8;
          text-decoration: none;
          font-size: 0.84rem;
          font-weight: 600;
          padding: 0.35rem 0.65rem;
          border-radius: 4px;
          border: 1px dashed #334155;
        ">Direct PDF ↗</a>

        <!-- Knowledge Base Links -->
        <span style="color: #475569; margin: 0 0.2rem;">|</span>
        <span style="font-size: 0.75rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">Knowledge:</span>

        <a href="/knowledge/setup-archetypes-mechanics.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">Archetypes</a>
        <a href="/knowledge/execution-protocols-risk-governance.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">Risk Protocols</a>
        <a href="/knowledge/turn-of-the-month.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">TOM Inflows</a>
        <a href="/knowledge/opex-gamma-dynamics.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">OpEx Gamma</a>
        <a href="/knowledge/macro-event-guardrails.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">Binary Guardrails</a>
        <a href="/knowledge/midterm-structural-cycles.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">Midterm Cycles</a>
        <a href="/knowledge/zacks-rank-revisions.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">Zacks Rank</a>
        <a href="/knowledge/russell-reconstitution.html" style="color: #94a3b8; text-decoration: none; font-size: 0.82rem; font-weight: 500;">Index Inclusion</a>
      </nav>
    </header>
  `;

  document.addEventListener('DOMContentLoaded', function() {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = navHtml.trim();
    document.body.insertAdjacentElement('afterbegin', tempDiv.firstElementChild);
  });
})();