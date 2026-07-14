// @ts-check
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  // D-14: this is a GitHub Pages *project* page (jadrianports.github.io/dexter),
  // not a user/org root page. BOTH `site` and `base` are required — `site` alone
  // does not fix asset/link resolution under the subpath. Omitting `base` (or
  // getting it wrong) is the classic failure mode: the page works perfectly
  // under `astro dev` (served at `/`) and then every asset 404s once deployed,
  // because `astro:assets`/`Astro.url`-derived paths prepend `base` automatically
  // but nothing else does. Do not "simplify" this to just `site`.
  site: 'https://jadrianports.github.io',
  base: '/dexter',
});
