<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import PlaceArt from '$lib/components/PlaceArt.svelte';
	import { api } from '$lib/api';
	import { money, tone, unitLabel, type Hunt, type Listing } from '$lib/listing';
	import { loadMarks, saveMarks } from '$lib/marks';

	let listings = $state<Listing[]>([]);
	let index = $state(0);
	let stars = $state(0);
	let slug = $derived($page.params.slug ?? '');
	let current = $derived(listings[index] ?? null);

	onMount(() => {
		const saved = loadMarks();
		void load().then(() => {
			const listing = listings[index];
			if (listing) stars = saved[listing.id]?.stars ?? 0;
		});
	});

	async function load() {
		const response = await api('/api/v1/hunts');
		if (!response.ok) {
			window.location.href = '/login';
			return;
		}
		const hunts = ((await response.json()) as { hunts: Hunt[] }).hunts;
		const found = hunts.find((item) => item.slug === slug);
		if (!found) return;
		const listed = await api(
			`/api/v1/listings?hunt_id=${found.id}&presentable=true&sort=hunt_score&limit=20`
		);
		if (listed.ok) listings = ((await listed.json()) as { listings: Listing[] }).listings;
	}

	function remember() {
		const listing = listings[index];
		if (!listing || !stars) return;
		const marks = loadMarks();
		marks[listing.id] = { ...marks[listing.id], stars };
		saveMarks(marks);
	}

	function next() {
		remember();
		stars = 0;
		index = Math.min(listings.length - 1, index + 1);
		const listing = listings[index];
		if (listing) stars = loadMarks()[listing.id]?.stars ?? 0;
	}
</script>

<div class="stage">
	{#if current}
		<div class="phone" style:background={tone(current.short_id)}>
			<PlaceArt />
			<div class="top">
				<div class="bars">
					{#each listings as listing, bar (listing.id)}
						<span class:on={bar <= index}></span>
					{/each}
				</div>
				<div class="row">
					<a href="/h/{slug}">Dwellings</a>
					<span class="mono"><em>{current.hunt_score ?? '—'}</em> hunt · {index + 1} / {listings.length}</span>
				</div>
			</div>
			{#if current.unavailable_date}
				<div class="gone">No longer available</div>
			{/if}
			<div class="sheet">
				<span class="kicker">{current.neighborhood ?? '—'} · {current.borough_or_city ?? ''}</span>
				<h1>{current.title}</h1>
				<div class="pills">
					<span>{money(current.price)}</span>
					<span>{unitLabel(current)}</span>
					<span>{current.geo_bucket ?? '—'}</span>
				</div>
				<p>{current.fit_reasons[0] ?? current.notes ?? 'A place the hunt can still reach.'}</p>
				<div class="actions">
					<button type="button" aria-label="Pass" onclick={next}>✕</button>
					<div>
						{#each [1, 2, 3, 4, 5] as star (star)}
							<button type="button" aria-label="{star} stars" onclick={() => (stars = star)}>
								{stars >= star ? '★' : '☆'}
							</button>
						{/each}
					</div>
					<button type="button" class="love" aria-label="Love" onclick={() => { stars = 5; next(); }}>♥</button>
				</div>
			</div>
		</div>
	{:else}
		<p class="empty">Nothing presentable in this hunt yet.</p>
	{/if}
</div>

<style>
	.stage {
		min-height: 100vh;
		display: grid;
		place-items: center;
		background: #070706;
	}

	.phone {
		width: 390px;
		height: 844px;
		max-height: 100vh;
		position: relative;
		overflow: hidden;
		color: var(--text);
	}

	.top {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		padding: 20px 20px 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.bars {
		display: flex;
		gap: 4px;
	}

	.bars span {
		flex: 1;
		height: 3px;
		border-radius: 2px;
		background: rgba(243, 239, 231, 0.28);
	}

	.bars span.on {
		background: var(--text);
	}

	.row,
	.actions,
	.pills {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
	}

	.row a {
		font-family: var(--font-display);
		font-style: italic;
		font-size: 22px;
		text-decoration: none;
	}

	.mono {
		padding: 6px 12px;
		border-radius: 999px;
		background: rgba(15, 14, 12, 0.72);
		font-family: var(--font-mono);
		font-size: 12px;
	}

	.mono em {
		color: var(--ok);
		font-style: normal;
	}

	.gone {
		position: absolute;
		top: 230px;
		left: 0;
		right: 0;
		text-align: center;
		font-family: var(--font-display);
		font-style: italic;
		font-size: 24px;
	}

	.sheet {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		padding: 120px 20px 28px;
		background: linear-gradient(to top, rgba(15, 14, 12, 0.97) 55%, rgba(15, 14, 12, 0));
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.kicker {
		font-size: 11px;
		letter-spacing: 1.6px;
		text-transform: uppercase;
		color: var(--muted);
	}

	h1 {
		margin: 0;
		font-family: var(--font-display);
		font-weight: 400;
		font-size: 34px;
		line-height: 1.05;
	}

	.pills span {
		padding: 6px 10px;
		border: 1px solid #3a3833;
		border-radius: 999px;
		font-family: var(--font-mono);
		font-size: 12px;
	}

	p {
		margin: 0;
		color: #d6d1c7;
		line-height: 1.45;
	}

	button {
		border: 0;
		background: transparent;
		color: inherit;
		cursor: pointer;
	}

	.actions > button {
		width: 56px;
		height: 56px;
		border-radius: 50%;
		border: 1px solid #3a3833;
		background: rgba(15, 14, 12, 0.6);
		font-size: 22px;
	}

	.love {
		background: var(--love);
		color: var(--ground);
		border: 0;
	}

	.empty {
		color: var(--muted);
	}
</style>
