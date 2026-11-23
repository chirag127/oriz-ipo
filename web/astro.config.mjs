// @ts-check
import { defineConfig } from 'astro/config';

// Static dark GMP-terminal site for ipo.oriz.in. Reads ../data/latest.json at
// build time (the scraper commits it hourly; CF Pages rebuilds on push).
//
// PAGES_BASE lets the same source build for two hosts:
//   Cloudflare Pages -> '/' (ipo.oriz.in)
//   GitHub Pages     -> '/oriz-ipo/' (gh.oriz.in/oriz-ipo/)
const base = process.env.PAGES_BASE || '/';

export default defineConfig({
  site: 'https://ipo.oriz.in',
  base,
  output: 'static',
  trailingSlash: 'ignore',
});
