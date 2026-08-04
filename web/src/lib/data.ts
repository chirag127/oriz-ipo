import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
// Astro runs from web/; data lives at ../data. Resolve from cwd first
// (stable at build), fall back to a path relative to this module.
const CANDIDATES = [
  path.resolve(process.cwd(), '../data/latest.json'),
  path.resolve(here, '../../../data/latest.json'),
];

export interface ReviewVideo {
  title: string;
  url: string;
  channel: string;
  views: number;
  upload_date: string;
  sentiment: string;
}
export interface Ipo {
  name: string;
  gmp: number | null;
  gmp_pct: number | null;
  price_band: string;
  ipo_type: string;
  status: string;
  source: string;
  review_score: number;
  videos: ReviewVideo[];
  summary: string;
  slug: string;
}
export interface Snapshot {
  generated_at: string;
  source: string;
  threshold_pct: number;
  count_all: number;
  count_picks: number;
  all_ipos: Ipo[];
  picks: Ipo[];
}

const EMPTY: Snapshot = {
  generated_at: '',
  source: '',
  threshold_pct: 5,
  count_all: 0,
  count_picks: 0,
  all_ipos: [],
  picks: [],
};

export function loadSnapshot(): Snapshot {
  for (const p of CANDIDATES) {
    try {
      return { ...EMPTY, ...JSON.parse(fs.readFileSync(p, 'utf-8')) };
    } catch {
      /* try next */
    }
  }
  return EMPTY;
}
