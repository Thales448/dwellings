import { describe, expect, it } from 'vitest';
import {
	bedBucket,
	lastCheckedAt,
	matchesBedFilter,
	parseUtc,
	seenLabel,
	type Listing
} from './listing';

function listing(overrides: Partial<Listing> = {}): Listing {
	return {
		id: '1',
		hunt_id: 'h',
		short_id: 1,
		title: 't',
		price: 2800,
		neighborhood: null,
		borough_or_city: null,
		status: 'alive',
		unit_kind: 'full_1br',
		beds: 1,
		beds_label: '1BR',
		hunt_score: 7,
		scam_risk: null,
		is_presentable: true,
		unavailable_date: null,
		source: 'craigslist',
		url: 'https://example.com',
		first_seen: '2026-10-07T12:00:00.000000',
		last_seen: '2026-10-07T12:00:00.000000',
		availability_checked_at: null,
		notes: null,
		honesty_flags: [],
		fit_reasons: [],
		attrs: {},
		geo_bucket: null,
		photos: [],
		link_check: { ok: true, error: null, checked_at: '2026-10-07T12:05:00.000000' },
		...overrides
	};
}

describe('parseUtc / seenLabel', () => {
	it('treats naive timestamps as UTC so they are not zero minutes ago', () => {
		const past = '2026-10-07T12:00:00.000000';
		const ms = parseUtc(past);
		expect(ms).toBe(Date.parse('2026-10-07T12:00:00.000000Z'));
		expect(seenLabel(past)).not.toBe('0m ago');
	});
});

describe('lastCheckedAt', () => {
	it('falls back from availability_checked_at to link_check.checked_at', () => {
		expect(lastCheckedAt(listing())).toBe('2026-10-07T12:05:00.000000');
		expect(
			lastCheckedAt(listing({ availability_checked_at: '2026-10-07T13:00:00.000000Z' }))
		).toBe('2026-10-07T13:00:00.000000Z');
	});
});

describe('bed filters (feed floor)', () => {
	it('classifies studio, 1BR, and 2BR including full_2br_plus', () => {
		expect(bedBucket(listing({ unit_kind: 'full_studio', beds: 0, beds_label: '0BR' }))).toBe(
			'studio'
		);
		expect(bedBucket(listing({ unit_kind: 'full_1br', beds: 1, beds_label: '1BR' }))).toBe('1br');
		expect(bedBucket(listing({ unit_kind: 'full_2br_plus', beds: 2, beds_label: '2BR' }))).toBe(
			'2br'
		);
	});

	it('keeps RI stretch studios/1BRs when bedroom floor filters are active', () => {
		const ri = listing({
			unit_kind: 'full_1br',
			price: 3800,
			attrs: { is_roosevelt_island: true },
			is_presentable: true
		});
		expect(matchesBedFilter(ri, ['studio', '1br', '2br'])).toBe(true);
		expect(matchesBedFilter(ri, ['1br'])).toBe(true);
		expect(matchesBedFilter(ri, ['2br'])).toBe(false);
	});
});
