import { a as attr } from "../../../chunks/attributes.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let loading = false;
    $$renderer2.push(`<h1>Models</h1> <p style="color:var(--text-dim);margin-bottom:1rem;font-size:0.85rem">Train Poisson / Dixon-Coles models on historical match data.</p> <div class="stat-grid" style="grid-template-columns:1fr 1fr 1fr"><div class="card" style="display:flex;flex-direction:column;gap:0.5rem"><h3>1. Import Data</h3> <p style="font-size:0.8rem;color:var(--text-dim)">Load 60 historical matches from CSV</p> <button${attr("disabled", loading, true)}>📥 Import CSV</button></div> <div class="card" style="display:flex;flex-direction:column;gap:0.5rem"><h3>2. Train Model</h3> <p style="font-size:0.8rem;color:var(--text-dim)">Fit Poisson + Dixon-Coles MLE models</p> <button${attr("disabled", loading, true)}>🧠 Fit Model</button></div> <div class="card" style="display:flex;flex-direction:column;gap:0.5rem"><h3>3. Evaluate</h3> <p style="font-size:0.8rem;color:var(--text-dim)">Calibration + backtest on holdout</p> <button${attr("disabled", loading, true)}>📊 Fit + Eval</button></div></div> <div class="card mt-1"><h3>Data Expansion</h3> <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:0.5rem">Fetch real match data from football-data.org (requires API key)</p> <button${attr("disabled", loading, true)} class="btn-outline">🌐 Expand to 1,000+ matches</button></div> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  _page as default
};
