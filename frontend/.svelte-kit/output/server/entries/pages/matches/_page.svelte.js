import { e as ensure_array_like, a as attr_class } from "../../../chunks/index2.js";
import { e as escape_html, a as attr } from "../../../chunks/attributes.js";
import { a as api } from "../../../chunks/api.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let matches = [];
    let loading = true;
    let filter = "live";
    async function refresh() {
      loading = true;
      try {
        matches = await api.listMatches(filter === "all" ? void 0 : filter);
      } catch {
      }
      loading = false;
    }
    $$renderer2.push(`<div class="flex mb-2"><h1>Matches</h1> <div class="flex gap-sm" style="margin-left:auto">`);
    $$renderer2.select({ value: filter, onchange: refresh }, ($$renderer3) => {
      $$renderer3.option({ value: "live" }, ($$renderer4) => {
        $$renderer4.push(`Live`);
      });
      $$renderer3.option({ value: "upcoming" }, ($$renderer4) => {
        $$renderer4.push(`Upcoming`);
      });
      $$renderer3.option({ value: "finished" }, ($$renderer4) => {
        $$renderer4.push(`Finished`);
      });
      $$renderer3.option({ value: "all" }, ($$renderer4) => {
        $$renderer4.push(`All`);
      });
    });
    $$renderer2.push(` <button>↻</button></div></div> `);
    if (loading) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<p>Loading...</p>`);
    } else if (matches.length === 0) {
      $$renderer2.push("<!--[1-->");
      $$renderer2.push(`<div class="card"><p style="color:var(--text-dim);text-align:center">No matches found</p></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="card" style="overflow-x:auto"><table><thead><tr><th>Home</th><th>Away</th><th>League</th><th>Score</th><th>Status</th><th>Odds</th><th>Action</th></tr></thead><tbody><!--[-->`);
      const each_array = ensure_array_like(matches);
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let m = each_array[$$index];
        $$renderer2.push(`<tr><td><strong>${escape_html(m.home_team)}</strong></td><td>${escape_html(m.away_team)}</td><td><span class="tag">${escape_html(m.league)}</span></td><td class="mono">${escape_html(m.home_score ?? "-")} : ${escape_html(m.away_score ?? "-")}</td><td><span${attr_class("badge", void 0, {
          "badge-green": m.status === "live",
          "badge-blue": m.status === "upcoming"
        })}>${escape_html(m.status)}</span></td><td class="mono">${escape_html(m.betfair_market_id ? "BF" : "")}${escape_html(m.smarkets_market_id ? " SM" : "")}</td><td><a${attr("href", `/matches/${m.id}`)} class="btn btn-outline" style="padding:0.25rem 0.5rem;font-size:0.75rem">View</a></td></tr>`);
      }
      $$renderer2.push(`<!--]--></tbody></table></div>`);
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  _page as default
};
