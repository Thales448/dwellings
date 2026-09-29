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

export function seenLabel(iso: string): string {
	const then = new Date(iso).getTime();
	if (Number.isNaN(then)) return iso;
	const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.round(minutes / 60);
	if (hours < 48) return `${hours}h ago`;
	return new Date(iso).toLocaleDateString();
}
