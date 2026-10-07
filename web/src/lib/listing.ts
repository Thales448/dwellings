export type Photo = {
	id: string;
	position: number;
	caption: string | null;
	is_cover: boolean;
	width: number;
	height: number;
	shows_kitchen: boolean | null;
	url: string;
	thumb: string;
};

export type Listing = {
	id: string;
	hunt_id: string;
	short_id: number;
	title: string;
	price: number;
	neighborhood: string | null;
	borough_or_city: string | null;
	status: string;
	unit_kind: string;
	beds: number | null;
	beds_label: string | null;
	hunt_score: number | null;
	scam_risk: string | null;
	is_presentable: boolean;
	unavailable_date: string | null;
	source: string;
	url: string;
	first_seen: string;
	last_seen: string;
	availability_checked_at: string | null;
	notes: string | null;
	honesty_flags: string[];
	fit_reasons: string[];
	attrs: Record<string, unknown>;
	geo_bucket: string | null;
	photos?: Photo[];
	link_check?: { ok: boolean; error: string | null; checked_at: string | null };
};

export type Hunt = {
	id: string;
	slug: string;
	name: string;
	kind: string;
	schema: string;
	criteria: Record<string, unknown>;
	role: string;
};

/** Presentable unit floor on the feed: studio, 1BR, and couple 2BR+. */
export type BedFilter = 'studio' | '1br' | '2br';

export const BED_FILTERS: BedFilter[] = ['studio', '1br', '2br'];

const TONES = ['#3A3129', '#2C3338', '#3A2E2A', '#243036', '#3B3428', '#2A2E38'];

export function money(value: number): string {
	return new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency: 'USD',
		maximumFractionDigits: 0
	}).format(value);
}

export function tone(id: number): string {
	return TONES[id % TONES.length];
}

export function unitLabel(listing: Listing): string {
	if (listing.beds_label === 'studio' || listing.unit_kind === 'full_studio') return 'Studio';
	if (listing.beds_label) return listing.beds_label.replace('br', ' BR');
	return listing.unit_kind.replaceAll('_', ' ');
}

export function queueTag(listing: Listing): { text: string; color: string } {
	if (listing.status === 'dead' || listing.status === 'rented' || listing.unavailable_date) {
		return { text: 'Gone · kept', color: '#A39E93' };
	}
	if (listing.scam_risk === 'high' || listing.status === 'scam') {
		return { text: 'Likely scam', color: '#F07D80' };
	}
	if (listing.status === 'demoted' || listing.status === 'watching') {
		return { text: listing.status, color: '#E0B45A' };
	}
	return { text: 'New', color: '#8FB996' };
}

/** Treat naive ISO timestamps as UTC — API historically omitted the offset. */
export function parseUtc(iso: string): number {
	const trimmed = iso.trim();
	if (!trimmed) return Number.NaN;
	const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed);
	return new Date(hasZone ? trimmed : `${trimmed}Z`).getTime();
}

export function seenLabel(iso: string): string {
	const then = parseUtc(iso);
	if (Number.isNaN(then)) return iso;
	const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.round(minutes / 60);
	if (hours < 48) return `${hours}h ago`;
	return new Date(then).toLocaleDateString();
}

/** Genuine last check: agent recheck, else Craigslist link verify, else last_seen. */
export function lastCheckedAt(listing: Listing): string | null {
	return (
		listing.availability_checked_at ||
		listing.link_check?.checked_at ||
		listing.last_seen ||
		null
	);
}

export function coverPhoto(listing: Listing): Photo | null {
	const photos = listing.photos ?? [];
	if (!photos.length) return null;
	return photos.find((photo) => photo.is_cover) ?? photos[0];
}

export function bedBucket(listing: Listing): BedFilter | null {
	if (listing.unit_kind === 'full_studio' || listing.beds_label === 'studio' || listing.beds === 0) {
		return 'studio';
	}
	if (listing.unit_kind === 'full_1br' || listing.beds_label === '1BR' || listing.beds === 1) {
		return '1br';
	}
	if (
		listing.unit_kind === 'full_2br_plus' ||
		listing.beds_label === '2BR' ||
		(listing.beds != null && listing.beds >= 2)
	) {
		return '2br';
	}
	return null;
}

export function matchesBedFilter(listing: Listing, selected: BedFilter[]): boolean {
	if (!selected.length) return false;
	const bucket = bedBucket(listing);
	return bucket != null && selected.includes(bucket);
}

export function bedFilterLabel(filter: BedFilter): string {
	if (filter === 'studio') return 'Studio';
	if (filter === '1br') return '1 BR';
	return '2 BR';
}
