import { a as attr_class, e as ensure_array_like, s as store_get, a3 as derived, u as unsubscribe_stores } from "../../../chunks/index2.js";
import { e as escape_html } from "../../../chunks/attributes.js";
import { a as api } from "../../../chunks/api.js";
import { w as writable } from "../../../chunks/index.js";
const activeBankrollId = writable(null);
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    let trades = [];
    let filter = "all";
    async function refresh() {
      const bid = store_get($$store_subs ??= {}, "$activeBankrollId", activeBankrollId);
      if (bid) trades = await api.listTrades(bid, void 0);
    }
    let totalPnl = derived(() => trades.reduce((s, t) => s + Number(t.profit_loss || 0), 0));
    let wins = derived(() => trades.filter((t) => t.final_result === "won").length);
    let losses = derived(() => trades.filter((t) => t.final_result === "lost").length);
    $$renderer2.push(`<div class="flex mb-2"><h1>Trade Log</h1> <div class="flex gap-sm" style="margin-left:auto">`);
    $$renderer2.select({ value: filter, onchange: refresh }, ($$renderer3) => {
      $$renderer3.option({ value: "all" }, ($$renderer4) => {
        $$renderer4.push(`All`);
      });
      $$renderer3.option({ value: "filled" }, ($$renderer4) => {
        $$renderer4.push(`Open`);
      });
      $$renderer3.option({ value: "settled" }, ($$renderer4) => {
        $$renderer4.push(`Settled`);
      });
    });
    $$renderer2.push(` <button>↻</button></div></div> <div class="stat-grid"><div class="card"><div class="stat-label">Total Trades</div><div class="stat-value">${escape_html(trades.length)}</div></div> <div class="card"><div class="stat-label">Wins</div><div class="stat-value positive svelte-4z9rsc">${escape_html(wins())}</div></div> <div class="card"><div class="stat-label">Losses</div><div class="stat-value negative svelte-4z9rsc">${escape_html(losses())}</div></div> <div class="card"><div class="stat-label">Total P&amp;L</div><div${attr_class("stat-value mono svelte-4z9rsc", void 0, { "positive": totalPnl() >= 0, "negative": totalPnl() < 0 })}>$${escape_html(totalPnl().toFixed(2))}</div></div></div> <div class="card" style="overflow-x:auto">`);
    if (trades.length === 0) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<p style="color:var(--text-dim);text-align:center">No trades yet</p>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<table><thead><tr><th>Match</th><th>Bet</th><th>Odds</th><th>Edge</th><th>Stake</th><th>Result</th><th>P&amp;L</th></tr></thead><tbody><!--[-->`);
      const each_array = ensure_array_like(trades);
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let t = each_array[$$index];
        $$renderer2.push(`<tr><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escape_html(t.market_id)}</td><td><span class="tag">${escape_html(t.side)}</span></td><td class="mono">${escape_html(Number(t.requested_odds).toFixed(2))}</td><td class="mono">${escape_html(t.edge_at_entry ? (Number(t.edge_at_entry) * 100).toFixed(1) + "%" : "-")}</td><td class="mono">$${escape_html(Number(t.requested_stake).toFixed(2))}</td><td>`);
        if (t.final_result === "won") {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="badge badge-green">WON</span>`);
        } else if (t.final_result === "lost") {
          $$renderer2.push("<!--[1-->");
          $$renderer2.push(`<span class="badge badge-red">LOST</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`<span class="badge badge-blue">${escape_html(t.status)}</span>`);
        }
        $$renderer2.push(`<!--]--></td><td${attr_class("mono svelte-4z9rsc", void 0, {
          "positive": Number(t.profit_loss) >= 0,
          "negative": Number(t.profit_loss) < 0
        })}>${escape_html(t.profit_loss ? `$${Number(t.profit_loss).toFixed(2)}` : "-")}</td></tr>`);
      }
      $$renderer2.push(`<!--]--></tbody></table>`);
    }
    $$renderer2.push(`<!--]--></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _page as default
};
