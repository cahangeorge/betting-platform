import { a as attr, e as escape_html } from "../../chunks/attributes.js";
import "@sveltejs/kit/internal";
import "../../chunks/exports.js";
import "../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../chunks/root.js";
import "../../chunks/state.svelte.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let email = "";
    let password = "";
    let loading = false;
    $$renderer2.push(`<div class="login-page svelte-1uha8ag"><div class="login-card svelte-1uha8ag"><h1 class="svelte-1uha8ag">Betting Bot</h1> <p class="subtitle svelte-1uha8ag">Live Football Trading Platform</p> <form class="svelte-1uha8ag"><div class="form-group"><label for="email">Email</label> <input id="email" type="email"${attr("value", email)} placeholder="you@example.com" required=""/></div> <div class="form-group"><label for="password">Password</label> <input id="password" type="password"${attr("value", password)} placeholder="••••••••" required=""/></div> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> <div class="flex gap-sm"><button type="submit"${attr("disabled", loading, true)}>${escape_html("Sign In")}</button> <button type="button" class="btn-outline"${attr("disabled", loading, true)}>Register</button></div></form></div></div>`);
  });
}
export {
  _page as default
};
