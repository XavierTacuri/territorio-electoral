// Reused across map widgets (see MapPage.tsx) as the last-resort viewport when
// no official geometry is available. It is not derived from any campaign's
// data — it only keeps the basemap from ever defaulting to MapLibre's [0,0]
// world view, which reads as broken to users.
export const TERRITORIAL_FALLBACK_CENTER: [number, number] = [-78.78, -2.89];
export const TERRITORIAL_FALLBACK_ZOOM = 9;
