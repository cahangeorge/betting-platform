import { e as ensure_array_like, a as attr_class, d as derived } from "../../../chunks/index2.js";
import { e as escape_html, a as attr } from "../../../chunks/attributes.js";
import { a as api } from "../../../chunks/api.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let matches = [];
    let loading = true;
    let filter = "live";
    let page = 1;
    const pageSize = 20;
    let paginatedMatches = derived(() => {
      const start = (page - 1) * pageSize;
      return matches.slice(start, start + pageSize);
    });
    let totalPages = derived(() => Math.max(1, Math.ceil(matches.length / pageSize)));
    async function refresh() {
      loading = true;
      page = 1;
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
      $$renderer2.push(`<div class="card" style="overflow-x:auto"><table><thead><tr><th>Home</th><th>Away</th><th>League</th><th>Score</th><th>Status</th><th>Odds</th><th>Action</th></tr></thead><tbody><!--[-->`);
      const each_array = ensure_array_like(Array(6));
      for (let $$index_1 = 0, $$length = each_array.length; $$index_1 < $$length; $$index_1++) {
        each_array[$$index_1];
        $$renderer2.push(`<tr><!--[-->`);
        const each_array_1 = ensure_array_like(Array(7));
        for (let $$index = 0, $$length2 = each_array_1.length; $$index < $$length2; $$index++) {
          each_array_1[$$index];
          $$renderer2.push(`<td><div class="skeleton skeleton-line w80"></div></td>`);
        }
        $$renderer2.push(`<!--]--></tr>`);
      }
      $$renderer2.push(`<!--]--></tbody></table></div>`);
    } else if (matches.length === 0) {
      $$renderer2.push("<!--[1-->");
      $$renderer2.push(`<div class="card"><p style="color:var(--text-dim);text-align:center">No matches found</p></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="card" style="overflow-x:auto"><table><thead><tr><th>Home</th><th>Away</th><th>League</th><th>Score</th><th>Status</th><th>Odds</th><th>Action</th></tr></thead><tbody><!--[-->`);
      const each_array_2 = ensure_array_like(paginatedMatches());
      for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
        let m = each_array_2[$$index_2];
        $$renderer2.push(`<tr><td><strong>${escape_html(m.home_team)}</strong></td><td>${escape_html(m.away_team)}</td><td><span class="tag">${escape_html(m.league)}</span></td><td class="mono">${escape_html(m.home_score ?? "-")} : ${escape_html(m.away_score ?? "-")}</td><td><span${attr_class("badge", void 0, {
          "badge-green": m.status === "live",
          "badge-blue": m.status === "upcoming"
        })}>${escape_html(m.status)}</span></td><td class="mono">${escape_html(m.betfair_market_id ? "BF" : "")}${escape_html(m.smarkets_market_id ? " SM" : "")}</td><td><a${attr("href", `/matches/${m.id}`)} class="btn btn-outline" style="padding:0.25rem 0.5rem;font-size:0.75rem">View</a></td></tr>`);
      }
      $$renderer2.push(`<!--]--></tbody></table> `);
      if (totalPages() > 1) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="pagination"><button${attr("disabled", page <= 1, true)}>← Prev</button> <span class="page-info">Page ${escape_html(page)} / ${escape_html(totalPages())}</span> <button${attr("disabled", page >= totalPages(), true)}>Next →</button></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div>`);
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  _page as default
};
