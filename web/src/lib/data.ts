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
  lot_size: string;
  open_date: string;
  close_date: string;
  listing_date: string;
  est_listing: string;
  ipo_type: string;
  status: string;
  source: string;
  issue_size: string;
  sub_total: number | null;
  sub_qib: number | null;
  sub_nii: number | null;
  sub_retail: number | null;
  review_score: number;
  videos: ReviewVideo[];
  summary: string;
  comment_analysis: string;
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

// History: read every data/history/*.json for the archive page.
export interface HistoryEntry {
  date: string;
  generated_at: string;
  source: string;
  count_picks: number;
  top: { name: string; gmp_pct: number | null; slug: string }[];
}

const HISTORY_DIRS = [
  path.resolve(process.cwd(), '../data/history'),
  path.resolve(here, '../../../data/history'),
];

export function loadHistory(): HistoryEntry[] {
  for (const dir of HISTORY_DIRS) {
    try {
      const files = fs.readdirSync(dir).filter((f) => f.endsWith('.json'));
      const entries: HistoryEntry[] = files.map((f) => {
        const snap = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf-8'));
        return {
          date: f.replace(/\.json$/, ''),
          generated_at: snap.generated_at ?? '',
          source: snap.source ?? '',
          count_picks: snap.count_picks ?? (snap.picks?.length ?? 0),
          top: (snap.picks ?? []).slice(0, 5).map((p: Ipo) => ({
            name: p.name,
            gmp_pct: p.gmp_pct,
            slug: p.slug,
          })),
        };
      });
      entries.sort((a, b) => (a.date < b.date ? 1 : -1)); // newest first
      return entries;
    } catch {
      /* try next */
    }
  }
  return [];
}
