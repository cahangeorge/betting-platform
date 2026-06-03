import { e as ensure_array_like } from "../../../chunks/index2.js";
import { o as onDestroy } from "../../../chunks/index-server.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    onDestroy(() => {
    });
    $$renderer2.push(`<h1>Dashboard</h1> `);
    {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="stat-grid"><!--[-->`);
      const each_array = ensure_array_like(Array(6));
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        each_array[$$index];
        $$renderer2.push(`<div class="card"><div class="skeleton skeleton-line w60"></div> <div class="skeleton skeleton-block" style="margin-top:0.5rem"></div></div>`);
      }
      $$renderer2.push(`<!--]--></div> <div class="card"><div class="skeleton skeleton-line w40"></div> <div class="skeleton skeleton-chart"></div></div>`);
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  _page as default
};
