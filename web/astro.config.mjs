// @ts-check
import { defineConfig } from 'astro/config';

// Static dark GMP-terminal site for ipo.oriz.in. Reads ../data/latest.json at
// build time (the scraper commits it hourly; CF Pages rebuilds on push).
export default defineConfig({
  site: 'https://ipo.oriz.in',
  output: 'static',
  trailingSlash: 'ignore',
});
