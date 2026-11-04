import type { MarketReviewRegion } from '../types/analysis';

export type { MarketReviewRegion };

export const MARKET_REVIEW_REGION_ORDER: readonly MarketReviewRegion[] = ['cn', 'hk', 'us', 'jp', 'kr', 'tr'];

/** Server-side `both` keeps its historical five markets; newer markets (tr) are opt-in. */
export const MARKET_REVIEW_BOTH_REGIONS: readonly MarketReviewRegion[] = ['cn', 'hk', 'us', 'jp', 'kr'];

export function serializeMarketReviewRegions(regions: readonly MarketReviewRegion[]): string {
  const ordered = MARKET_REVIEW_REGION_ORDER.filter((region) => regions.includes(region));
  const isLegacyBoth = ordered.length === MARKET_REVIEW_BOTH_REGIONS.length
    && MARKET_REVIEW_BOTH_REGIONS.every((region) => ordered.includes(region));
  return isLegacyBoth ? 'both' : ordered.join(',');
}
