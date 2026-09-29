<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';

	let { current = '' } = $props();
	let hunts = $state<{ slug: string; name: string }[]>([]);

	onMount(async () => {
		const response = await api('/api/v1/hunts');
		if (!response.ok) return;
		const payload = (await response.json()) as { hunts: { slug: string; name: string }[] };
		hunts = payload.hunts;
	});

	function choose(event: Event) {
		const slug = (event.target as HTMLSelectElement).value;
		if (slug) window.location.href = `/h/${slug}`;
	}
</script>

{#if hunts.length}
	<label>
		Hunt
		<select aria-label="Hunt switcher" onchange={choose}>
			<option value="" selected={current === ''}>Choose a hunt</option>
			{#each hunts as hunt (hunt.slug)}
				<option value={hunt.slug} selected={hunt.slug === current}>{hunt.name}</option>
			{/each}
		</select>
	</label>
{/if}

<style>
	label {
		display: grid;
		gap: 4px;
		color: var(--muted);
		font-size: 0.85rem;
	}

	select {
		min-height: 44px;
		min-width: 180px;
		background: var(--raised);
		color: var(--text);
		border: 1px solid var(--line);
		border-radius: 8px;
		padding: 0 10px;
	}
</style>
