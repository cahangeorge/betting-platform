import { a as attr, e as escape_html } from "../../../chunks/attributes.js";
function _page($$renderer) {
  let loading = false;
  $$renderer.push(`<h1>Backtest</h1> <p style="color:var(--text-dim);margin-bottom:1rem;font-size:0.85rem">Use the CLI for full backtesting: <code>uv run python3 scripts/backtest_cli.py --stake 1000 --kelly 0.25 --edge 0.05</code></p> <div class="grid-2"><div class="card"><h3>Quick Eval</h3> <div style="display:flex;flex-direction:column;gap:1rem;margin-top:1rem"><button${attr("disabled", loading, true)}>${escape_html("▶ Run Fit & Evaluate")}</button> `);
  {
    $$renderer.push("<!--[-1-->");
  }
  $$renderer.push(`<!--]--></div></div> <div class="card"><h3>Full Backtest (CLI)</h3> <div style="margin-top:1rem;font-size:0.85rem;color:var(--text-dim);line-height:1.6"><p>Run the full backtesting engine from the terminal:</p> <pre style="background:var(--bg);padding:1rem;border-radius:var(--radius);margin-top:0.5rem;overflow-x:auto">cd /root/betting_platform/backend
uv run python3 scripts/backtest_cli.py \\
  --stake 1000 \\
  --kelly 0.25 \\
  --edge 0.05</pre> <p style="margin-top:0.5rem">Outputs: Sharpe ratio, max drawdown, profit factor, edge distribution, odds win rates, league breakdown, full trade log.</p></div></div></div>`);
}
export {
  _page as default
};
