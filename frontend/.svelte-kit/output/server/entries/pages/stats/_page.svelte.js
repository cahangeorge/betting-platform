import { a as attr_class, e as ensure_array_like } from "../../../chunks/index2.js";
import { e as escape_html, a as attr } from "../../../chunks/attributes.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let ingester = { running: false };
    let matches = [];
    $$renderer2.push(`<h1>Live Stats</h1> <p style="color:var(--text-dim);margin-bottom:1rem;font-size:0.85rem">Live match stats from football-data.org + Understat feeds.</p> <div class="stat-grid"><div class="card"><div class="stat-label">Stats Ingester</div> <div${attr_class("stat-value", void 0, { "positive": ingester.running })}>${escape_html("⏹ Stopped")}</div> <button style="margin-top:0.5rem;font-size:0.8rem">${escape_html("Start")} Ingester</button></div> <div class="card"><div class="stat-label">Live Matches</div> <div class="stat-value">${escape_html(matches.length)}</div></div></div> <div class="card"><h3>Live Matches</h3> `);
    if (matches.length === 0) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<p style="color:var(--text-dim);font-size:0.85rem">No live matches. Set a match to status="live" in the DB or through the API.</p>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<table><thead><tr><th>Match</th><th>Score</th><th>Momentum</th><th>Action</th></tr></thead><tbody><!--[-->`);
      const each_array = ensure_array_like(matches);
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let m = each_array[$$index];
        $$renderer2.push(`<tr><td>${escape_html(m.home_team)} vs ${escape_html(m.away_team)}</td><td class="mono">${escape_html(m.home_score ?? "-")} : ${escape_html(m.away_score ?? "-")}</td><td><button class="btn-outline" style="padding:0.2rem 0.4rem;font-size:0.75rem">View</button></td><td><a${attr("href", `/matches/${m.id}`)} class="btn-outline" style="padding:0.2rem 0.4rem;font-size:0.75rem">Details</a></td></tr>`);
      }
      $$renderer2.push(`<!--]--></tbody></table>`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
export {
  _page as default
};
