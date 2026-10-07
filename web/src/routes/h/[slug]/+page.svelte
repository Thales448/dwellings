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
		lastCheckedAt,
		matchesBedFilter,
		money,
		queueTag,
		seenLabel,
		tone,
		unitLabel,
		type BedFilter,
		type Hunt,
		type Listing
	} from '$lib/listing';
	import { loadMarks, saveMarks, type Mark } from '$lib/marks';

	const tags = ['kitchen', 'light', 'size', 'noise', 'building', 'commute', 'price', 'vibe'];
	const tourLabels = ['Skip', 'Maybe', 'Tour', 'Applied'];

	let hunts = $state<Hunt[]>([]);
	let listings = $state<Listing[]>([]);
	let index = $state(0);
	let marks = $state<Record<string, Mark>>({});
	let pulse = $state('no heartbeat yet');
	/** Feed floor: studio + 1BR + 2BR (incl. full_2br_plus ≤$3200). Does not drop RI stretch. */
	let bedFilters = $state<BedFilter[]>([...BED_FILTERS]);
	let slug = $derived($page.params.slug ?? '');
	let hunt = $derived(hunts.find((item) => item.slug === slug) ?? null);
	let floored = $derived(
		listings.filter((item) => item.is_presentable && matchesBedFilter(item, bedFilters))
	);
	let current = $derived(floored[index] ?? null);
	let unrated = $derived(floored.filter((item) => !marks[item.id]?.stars).length);

	onMount(() => {
		marks = loadMarks();
		window.addEventListener('keydown', onKey);
		void load();
		return () => window.removeEventListener('keydown', onKey);
	});

	function onKey(event: KeyboardEvent) {
		const target = event.target;
		if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
		const listing = floored[index];
		if ((event.key === 'j' || event.key === 'ArrowDown') && floored.length) {
			index = Math.min(floored.length - 1, index + 1);
		} else if ((event.key === 'k' || event.key === 'ArrowUp') && floored.length) {
			index = Math.max(0, index - 1);
		} else if (listing && event.key >= '1' && event.key <= '5') {
			setStar(listing.id, Number(event.key));
		} else if (listing && event.key.toLowerCase() === 't') {
			setTour(listing.id, 'Tour');
		} else if (listing && event.key.toLowerCase() === 's') {
			setTour(listing.id, 'Skip');
		} else if (event.key.toLowerCase() === 'h') {
			window.location.href = `/h/${slug}/wall`;
		} else if (event.key.toLowerCase() === 'g') {
			window.location.href = `/h/${slug}/wall?filter=gone`;
		} else {
			return;
		}
		event.preventDefault();
	}

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
			`/api/v1/listings?hunt_id=${found.id}&presentable=false&sort=hunt_score&limit=100`
		);
		if (!listed.ok) return;
		listings = ((await listed.json()) as { listings: Listing[] }).listings;
		index = 0;
		const agents = await api(`/api/v1/hunts/${found.id}/agents`);
		if (!agents.ok) return;
		const rows = (
			(await agents.json()) as {
				agents: { name: string; last_seen_at: string | null; revoked_at: string | null }[];
			}
		).agents.filter((agent) => !agent.revoked_at);
		const live = rows.find((agent) => agent.last_seen_at) ?? rows[0];
		pulse = live
			? `${live.name}${live.last_seen_at ? ` · ${seenLabel(live.last_seen_at)}` : ''}`
			: 'no heartbeat yet';
	}

	function write(id: string, patch: Mark) {
		marks = { ...marks, [id]: { ...marks[id], ...patch } };
		saveMarks(marks);
	}

	function stat(listing: Listing) {
		const kitchen = String(listing.attrs.kitchen_status ?? 'unknown');
		const minutes = listing.attrs.commute_gct_minutes;
		const island = Boolean(listing.attrs.is_roosevelt_island);
		return [
			{ k: 'Rent', v: money(listing.price), c: '#F3EFE7' },
			{ k: 'Unit', v: unitLabel(listing), c: '#F3EFE7' },
			{ k: 'To GCT', v: minutes == null ? '—' : `${minutes}m`, c: '#F3EFE7' },
			{ k: 'Kitchen', v: kitchen, c: kitchen === 'ok' ? '#8FB996' : '#E0B45A' },
			{ k: 'Budget', v: island ? 'RI stretch' : 'standard', c: island ? '#E0B45A' : '#F3EFE7' }
		];
	}

	function setStar(id: string, value: number) {
		write(id, { stars: value });
	}

	function setTour(id: string, value: string) {
		write(id, { tour: value });
	}

	function toggleTag(id: string, tag: string) {
		const currentTags = marks[id]?.tags ?? [];
		const next = currentTags.includes(tag)
			? currentTags.filter((item) => item !== tag)
			: [...currentTags, tag];
		write(id, { tags: next });
	}

	function toggleBed(filter: BedFilter) {
		const on = bedFilters.includes(filter);
		if (on && bedFilters.length === 1) return;
		bedFilters = on ? bedFilters.filter((item) => item !== filter) : [...bedFilters, filter];
		index = 0;
	}
</script>

<div class="screen">
	<Shell
		{slug}
		huntName={hunt?.name ?? 'Hunt'}
		{hunts}
		active="feed"
		{unrated}
		{pulse}
	/>
	<div class="body">
		<aside class="rail">
			<div class="rail-head">
				<span>Presentable</span>
				<span class="mono">by hunt score</span>
			</div>
			<div class="bed-filters" role="group" aria-label="Bedroom floor filters">
				{#each BED_FILTERS as filter (filter)}
					<button
						type="button"
						class:on={bedFilters.includes(filter)}
						onclick={() => toggleBed(filter)}
					>
						{bedFilterLabel(filter)}
					</button>
				{/each}
			</div>
			<div class="queue">
				{#each floored as listing, itemIndex (listing.id)}
					{@const tag = queueTag(listing)}
					<button
						type="button"
						class:selected={itemIndex === index}
						onclick={() => (index = itemIndex)}
					>
						{@const cover = coverPhoto(listing)}
						<div class="thumb" style:background={tone(listing.short_id)}>
							{#if cover}
								<img src={cover.thumb} alt="" loading="lazy" />
							{/if}
							<span>#{listing.short_id}</span>
						</div>
						<div class="meta">
							<span class="title">{listing.title}</span>
							<span class="mono sub">{money(listing.price)} · {listing.neighborhood ?? '—'}</span>
							<span class="tag" style:color={tag.color}>{tag.text}</span>
						</div>
					</button>
				{/each}
			</div>
			<p class="footnote">
				Floor shows presentable studios, 1BRs, and 2BRs (≤$3,200). RI stretch studios/1BRs to $4,000
				stay included. Bedroom chips filter that floor — they do not drop RI stretch.
			</p>
		</aside>

		<main>
			{#if current}
				{@const tag = queueTag(current)}
				{@const cover = coverPhoto(current)}
				{@const checked = lastCheckedAt(current)}
				<div class="stage" style:background={tone(current.short_id)}>
					{#if cover}
						<img class="cover" src={cover.url} alt={cover.caption ?? current.title} />
					{:else}
						<PlaceArt />
					{/if}
					{#if current.scam_risk === 'high'}
						<div class="banner">Likely scam — don't send money or documents before an in-person viewing.</div>
					{/if}
					<div class="chips">
						<span>#{current.short_id}</span>
						<span><em>{current.hunt_score ?? '—'}</em> hunt score</span>
						<span>{tag.text}</span>
					</div>
					{#if current.unavailable_date}
						<div class="stamp">
							<div>No longer available</div>
							<div class="mono">{current.unavailable_date}</div>
						</div>
					{/if}
				</div>
				<div class="lede">
					<span class="kicker">
						{current.neighborhood ?? '—'}, {current.borough_or_city ?? '—'} · {String(current.attrs.subway ?? 'subway')}
						· first seen {seenLabel(current.first_seen)}
						· last checked {checked ? seenLabel(checked) : '—'}
					</span>
					<h1>{current.title}</h1>
				</div>
				<div class="stats">
					{#each stat(current) as item (item.k)}
						<div>
							<span class="kicker">{item.k}</span>
							<span class="mono value" style:color={item.c}>{item.v}</span>
						</div>
					{/each}
				</div>
				<div class="rate">
					<div class="you">
						<span class="kicker">You</span>
						<div>
							{#each [1, 2, 3, 4, 5] as star (star)}
								<button type="button" aria-label="{star} stars" onclick={() => setStar(current.id, star)}>
									<svg viewBox="0 0 24 24" width="26" height="26">
										<polygon
											points="12 3 14.8 8.9 21 9.6 16.4 13.9 17.6 20 12 16.9 6.4 20 7.6 13.9 3 9.6 9.2 8.9"
											fill={(marks[current.id]?.stars ?? 0) >= star ? '#E8845C' : 'transparent'}
											stroke={(marks[current.id]?.stars ?? 0) >= star ? '#E8845C' : '#A39E93'}
										/>
									</svg>
								</button>
							{/each}
						</div>
					</div>
					<div class="partner">
						<span class="kicker">Partner · Combined</span>
						<span class="mono">{marks[current.id]?.stars ?? '—'} · <em>{marks[current.id]?.stars ?? '—'}</em></span>
					</div>
					<div class="tour">
						{#each tourLabels as label (label)}
							<button
								type="button"
								class:on={marks[current.id]?.tour === label}
								onclick={() => setTour(current.id, label)}
							>
								{label}
							</button>
						{/each}
					</div>
					<div class="step">
						<button type="button" aria-label="Previous listing" onclick={() => (index = Math.max(0, index - 1))}>↑</button>
						<button type="button" aria-label="Next listing" onclick={() => (index = Math.min(floored.length - 1, index + 1))}>↓</button>
					</div>
				</div>
				<div class="why">
					<span class="kicker">Tag why</span>
					{#each tags as tag (tag)}
						<button
							type="button"
							class:on={(marks[current.id]?.tags ?? []).includes(tag)}
							onclick={() => toggleTag(current.id, tag)}
						>
							{tag}
						</button>
					{/each}
				</div>
			{:else}
				<p class="empty">No listings in this hunt yet.</p>
			{/if}
		</main>

		<aside class="side">
			{#if current}
				<section class="scam" class:high={current.scam_risk === 'high'}>
					<div class="scam-head">
						<span class="kicker">Scam check</span>
						<span class="pill">{current.scam_risk ?? 'unknown'}</span>
					</div>
					<p>{current.scam_risk === 'high' ? 'High risk from the agent.' : 'No high-risk mark from the agent.'}</p>
					{#if current.unavailable_date}<span class="kept">Kept for history.</span>{/if}
				</section>
				<section>
					<span class="kicker">Why it fits</span>
					{#each current.fit_reasons as reason (reason)}
						<div class="fit"><span></span>{reason}</div>
					{:else}
						<p class="muted">No fit notes yet.</p>
					{/each}
				</section>
				<section>
					<span class="kicker">Honesty flags</span>
					<div class="flags">
						{#each current.honesty_flags as flag (flag)}
							<span>{flag}</span>
						{/each}
					</div>
					<p class="muted">{current.notes ?? ''}</p>
				</section>
				<section class="trail">
					<div><span>First seen</span><span class="mono">{seenLabel(current.first_seen)}</span></div>
					<div><span>Last checked</span><span class="mono">{checked ? seenLabel(checked) : '—'}</span></div>
					<div><span>Status</span><span class="mono">{current.status}</span></div>
				</section>
				<a class="open" href={current.url} target="_blank" rel="noreferrer">Open on {current.source}</a>
			{/if}
		</aside>
	</div>
</div>

<style>
	.screen {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		background: var(--ground);
	}

	.body {
		flex: 1;
		display: grid;
		grid-template-columns: 300px minmax(0, 1fr) 340px;
		min-height: 0;
	}

	.rail,
	.side {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 20px 18px;
	}

	.rail {
		border-right: 1px solid var(--line);
	}

	.side {
		border-left: 1px solid var(--line);
		padding: 24px 26px;
	}

	.rail-head,
	.scam-head,
	.trail div,
	.rate,
	.why {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}

	.rail-head {
		padding: 0 8px 10px;
		font-size: 12px;
		letter-spacing: 1.6px;
		text-transform: uppercase;
		color: var(--muted);
	}

	.queue {
		display: flex;
		flex-direction: column;
		gap: 4px;
		overflow: auto;
	}

	.queue button,
	.tour button,
	.why button,
	.step button,
	.you button {
		border: 0;
		background: transparent;
		cursor: pointer;
		color: inherit;
	}

	.queue button {
		display: flex;
		gap: 12px;
		align-items: center;
		padding: 10px 8px;
		border-radius: 12px;
		text-align: left;
	}

	.queue button.selected {
		background: var(--raised);
	}


	.bed-filters {
		display: flex;
		gap: 6px;
		padding: 0 8px 12px;
		flex-wrap: wrap;
	}

	.bed-filters button {
		height: 32px;
		padding: 0 12px;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: transparent;
		color: var(--text);
		cursor: pointer;
		font-size: 12px;
	}

	.bed-filters button.on {
		background: var(--text);
		color: var(--ground);
		border-color: transparent;
		font-weight: 600;
	}

	.thumb img,
	img.cover {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.thumb {
		position: relative;
		overflow: hidden;
	}

	.thumb span {
		position: relative;
		z-index: 1;
	}

	.thumb {
		width: 56px;
		height: 56px;
		border-radius: 8px;
		display: flex;
		align-items: flex-end;
		padding: 4px;
		box-sizing: border-box;
	}

	.thumb span,
	.chips span {
		font-family: var(--font-mono);
		font-size: 10px;
		padding: 1px 4px;
		border-radius: 4px;
		background: rgba(15, 14, 12, 0.75);
	}

	.meta {
		display: flex;
		flex-direction: column;
		gap: 3px;
		min-width: 0;
	}

	.title {
		font-family: var(--font-display);
		font-size: 15px;
	}

	.sub,
	.mono {
		font-family: var(--font-mono);
		color: var(--muted);
		font-size: 11px;
	}

	.tag {
		font-size: 11px;
		font-weight: 600;
	}

	.footnote,
	.muted,
	.kept,
	.empty {
		color: var(--muted);
		font-size: 12px;
		line-height: 1.5;
	}

	.footnote {
		margin-top: auto;
		border-top: 1px solid var(--line);
		padding-top: 12px;
	}

	main {
		padding: 22px 32px;
		display: flex;
		flex-direction: column;
		gap: 18px;
	}

	.stage {
		position: relative;
		height: 360px;
		border-radius: 16px;
		overflow: hidden;
	}

	.banner {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		padding: 12px 20px;
		background: var(--danger);
		color: #1a0b0b;
		font-weight: 600;
	}

	.chips {
		position: absolute;
		top: 16px;
		left: 20px;
		display: flex;
		gap: 8px;
	}

	.chips span {
		padding: 7px 12px;
		border-radius: 999px;
		font-size: 12px;
	}

	.chips em {
		color: var(--ok);
		font-style: normal;
	}

	.stamp {
		position: absolute;
		top: 60px;
		right: 44px;
		transform: rotate(-8deg);
		padding: 14px 22px;
		border: 3px solid var(--text);
		border-radius: 10px;
		font-family: var(--font-display);
		font-style: italic;
		font-size: 30px;
		text-align: center;
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
		font-size: 42px;
		line-height: 1.05;
		letter-spacing: -0.8px;
	}

	.stats {
		display: grid;
		grid-template-columns: repeat(5, minmax(0, 1fr));
		border-top: 1px solid var(--line);
		border-bottom: 1px solid var(--line);
	}

	.stats div {
		padding: 12px 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.value {
		font-size: 19px;
		color: var(--text);
	}

	.you,
	.partner {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.partner em {
		color: var(--love);
		font-style: normal;
	}

	.tour {
		display: flex;
		gap: 4px;
		padding: 4px;
		border: 1px solid var(--line);
		border-radius: 999px;
	}

	.tour button,
	.why button {
		height: 40px;
		padding: 0 16px;
		border-radius: 999px;
	}

	.tour button.on,
	.why button.on {
		background: var(--text);
		color: var(--ground);
		font-weight: 600;
	}

	.why button {
		height: 32px;
		border: 1px solid var(--line);
		font-size: 13px;
	}

	.step button {
		width: 44px;
		height: 44px;
		border-radius: 50%;
		border: 1px solid var(--line);
	}

	.scam {
		padding: 16px;
		border-radius: 14px;
		background: #191815;
		border: 1px solid var(--line);
	}

	.scam.high {
		border-color: #5a2427;
	}

	.pill {
		padding: 5px 10px;
		border-radius: 999px;
		background: var(--raised);
		font-size: 12px;
		font-weight: 700;
	}

	.fit {
		display: flex;
		gap: 10px;
		align-items: center;
	}

	.fit span {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--ok);
	}

	.flags {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	.flags span {
		padding: 5px 10px;
		border-radius: 6px;
		border: 1px solid #5a4a2a;
		color: var(--warn);
		font-family: var(--font-mono);
		font-size: 12px;
	}

	.trail div {
		padding: 7px 0;
		border-bottom: 1px solid #1f1e1b;
		font-size: 14px;
	}

	.open {
		display: flex;
		justify-content: space-between;
		padding: 13px 16px;
		border: 1px solid var(--line);
		border-radius: 12px;
		text-decoration: none;
	}

	section {
		display: flex;
		flex-direction: column;
		gap: 9px;
	}

	@media (max-width: 1100px) {
		.body {
			grid-template-columns: 1fr;
		}

		.rail,
		.side {
			border: 0;
		}
	}
</style>
