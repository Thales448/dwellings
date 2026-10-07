<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import PlaceArt from '$lib/components/PlaceArt.svelte';
	import Shell from '$lib/components/Shell.svelte';
	import { api } from '$lib/api';
	import {
		BED_FILTERS,
		bedFilterLabel,
		coverPhoto,
		matchesBedFilter,
		money,
		queueTag,
		tone,
		unitLabel,
		type BedFilter,
		type Hunt,
		type Listing
	} from '$lib/listing';
	import { loadMarks, type Mark } from '$lib/marks';

	let hunts = $state<Hunt[]>([]);
	let listings = $state<Listing[]>([]);
	let filter = $state('presentable');
	let bedFilters = $state<BedFilter[]>([...BED_FILTERS]);
	let marks = $state<Record<string, Mark>>({});
	let slug = $derived($page.params.slug ?? '');
	let hunt = $derived(hunts.find((item) => item.slug === slug) ?? null);

	let shown = $derived.by(() => {
		let rows: Listing[];
		if (filter === 'gone') {
			rows = listings.filter((item) => item.status === 'dead' || item.status === 'rented');
		} else if (filter === 'flagged') {
			rows = listings.filter((item) => item.scam_risk === 'high');
		} else if (filter === 'unrated') {
			rows = listings.filter((item) => !marks[item.id]?.stars);
		} else if (filter === 'tour') {
			rows = listings.filter((item) => marks[item.id]?.tour === 'Tour' || item.status === 'watching');
		} else {
			rows = listings.filter((item) => item.is_presentable);
		}
		// Bedroom/floor chips: studio + 1BR + 2BR; never drop RI stretch via price.
		return rows.filter((item) => matchesBedFilter(item, bedFilters));
	});

	let columns = $derived.by(() => {
		const cols: Listing[][] = [[], [], [], []];
		shown.forEach((item, index) => cols[index % 4].push(item));
		return cols;
	});

	onMount(() => {
		marks = loadMarks();
		filter = new URLSearchParams(window.location.search).get('filter') ?? 'presentable';
		void load();
	});

	async function load() {
		const response = await api('/api/v1/hunts');
		if (!response.ok) {
			window.location.href = '/login';
			return;
		}
		hunts = ((await response.json()) as { hunts: Hunt[] }).hunts;
		const found = hunts.find((item) => item.slug === slug);
		if (!found) return;
		const listed = await api(
			`/api/v1/listings?hunt_id=${found.id}&presentable=false&sort=hunt_score&limit=50`
		);
		if (listed.ok) listings = ((await listed.json()) as { listings: Listing[] }).listings;
	}

	function pick(next: string) {
		filter = next;
		const url = next === 'presentable' ? `/h/${slug}/wall` : `/h/${slug}/wall?filter=${next}`;
		history.replaceState(null, '', url);
	}

	function toggleBed(next: BedFilter) {
		const on = bedFilters.includes(next);
		if (on && bedFilters.length === 1) return;
		bedFilters = on ? bedFilters.filter((item) => item !== next) : [...bedFilters, next];
	}
</script>

<div class="screen">
	<Shell {slug} huntName={hunt?.name ?? 'Hunt'} {hunts} active={filter === 'gone' ? 'gone' : 'wall'} />
	<div class="headline">
		<div>
			<span class="kicker">This week's finds</span>
			<h1>{shown.length} places, <em>one</em> worth touring.</h1>
		</div>
		<div class="chips">
			<button type="button" class:on={filter === 'presentable'} onclick={() => pick('presentable')}>Presentable {listings.filter((item) => item.is_presentable).length}</button>
			<button type="button" class:on={filter === 'unrated'} onclick={() => pick('unrated')}>Unrated {listings.filter((item) => !marks[item.id]?.stars).length}</button>
			<button type="button" class:on={filter === 'tour'} onclick={() => pick('tour')}>Tour</button>
			<button type="button" class="flag" class:on={filter === 'flagged'} onclick={() => pick('flagged')}>Flagged {listings.filter((item) => item.scam_risk === 'high').length}</button>
			<button type="button" class:on={filter === 'gone'} onclick={() => pick('gone')}>Gone</button>
			<button type="button">Sort · Best fit</button>
			<span class="sep" aria-hidden="true"></span>
			{#each BED_FILTERS as bed (bed)}
				<button type="button" class:on={bedFilters.includes(bed)} onclick={() => toggleBed(bed)}>{bedFilterLabel(bed)}</button>
			{/each}
		</div>
	</div>
	<div class="grid">
		{#each columns as column, columnIndex (columnIndex)}
			<div class="col">
				{#each column as listing (listing.id)}
					{@const tag = queueTag(listing)}
					{@const cover = coverPhoto(listing)}
					<a class="card" href="/h/{slug}">
						<div class="photo" style:background={tone(listing.short_id)} style:height={listing.short_id % 2 ? '280px' : '220px'}>
							{#if cover}
								<img class="cover" src={cover.thumb} alt="" loading="lazy" />
							{:else}
								<PlaceArt />
							{/if}
							<span class="score"><em>{listing.hunt_score ?? '—'}</em> hunt</span>
							{#if (marks[listing.id]?.stars ?? 0) >= 4}<span class="love">♥</span>{/if}
							{#if listing.scam_risk === 'high'}<div class="strip">Likely scam</div>{/if}
							{#if listing.unavailable_date}<div class="gone">No longer available</div>{/if}
						</div>
						<span class="kicker">{listing.neighborhood ?? '—'}</span>
						<span class="title">{listing.title}</span>
						<span class="mono">{money(listing.price)} · {unitLabel(listing)} <em style:color={tag.color}>{tag.text}</em></span>
					</a>
				{/each}
			</div>
		{/each}
	</div>
</div>

<style>
	.screen {
		min-height: 100vh;
		background: var(--ground);
	}

	.headline {
		padding: 36px 32px 24px;
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 24px;
	}

	.kicker {
		font-size: 12px;
		letter-spacing: 1.6px;
		text-transform: uppercase;
		color: var(--muted);
	}

	h1 {
		margin: 8px 0 0;
		font-family: var(--font-display);
		font-weight: 400;
		font-size: 52px;
		letter-spacing: -1px;
		line-height: 1;
	}

	h1 em {
		color: var(--love);
	}

	.chips {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.chips button {
		height: 44px;
		padding: 0 18px;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: transparent;
		color: var(--text);
		cursor: pointer;
	}

	.chips button.on {
		background: var(--text);
		color: var(--ground);
		border-color: transparent;
		font-weight: 600;
	}

	.flag {
		color: var(--danger-text);
		border-color: #5a2427;
	}

	.grid {
		padding: 0 32px 40px;
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 20px;
		align-items: start;
	}

	.col,
	.card {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.card {
		text-decoration: none;
		gap: 5px;
	}


	.sep {
		width: 1px;
		height: 28px;
		background: var(--line);
		align-self: center;
	}

	.photo img.cover {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.photo {
		position: relative;
		border-radius: 14px;
		overflow: hidden;
	}

	.score {
		position: absolute;
		top: 12px;
		left: 12px;
		padding: 5px 10px;
		border-radius: 999px;
		background: rgba(15, 14, 12, 0.72);
		font-family: var(--font-mono);
		font-size: 11px;
	}

	.score em {
		color: var(--ok);
		font-style: normal;
	}

	.love {
		position: absolute;
		top: 12px;
		right: 12px;
		width: 28px;
		height: 28px;
		border-radius: 50%;
		background: var(--love);
		color: var(--ground);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.strip,
	.gone {
		position: absolute;
		left: 0;
		right: 0;
	}

	.strip {
		bottom: 0;
		padding: 10px 12px;
		background: var(--danger);
		color: #1a0b0b;
		font-weight: 700;
	}

	.gone {
		top: 42%;
		text-align: center;
		font-family: var(--font-display);
		font-style: italic;
	}

	.title {
		font-family: var(--font-display);
		font-size: 22px;
		line-height: 1.15;
	}

	.mono {
		font-family: var(--font-mono);
		font-size: 13px;
	}

	@media (max-width: 1100px) {
		.grid {
			grid-template-columns: 1fr 1fr;
		}

		h1 {
			font-size: 36px;
		}

		.headline {
			flex-direction: column;
			align-items: flex-start;
		}
	}
</style>
