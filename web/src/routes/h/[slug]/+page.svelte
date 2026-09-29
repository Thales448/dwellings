<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import HuntSwitcher from '$lib/components/HuntSwitcher.svelte';
	import { api } from '$lib/api';

	let slug = $derived($page.params.slug ?? '');
	let hunt = $state<{ name: string; role: string; kind: string } | null>(null);
	let missing = $state(false);

	onMount(async () => {
		const response = await api('/api/v1/hunts');
		if (!response.ok) {
			window.location.href = '/login';
			return;
		}
		const payload = (await response.json()) as {
			hunts: { slug: string; name: string; role: string; kind: string }[];
		};
		hunt = payload.hunts.find((item) => item.slug === slug) ?? null;
		missing = hunt === null;
	});
</script>

<main>
	<HuntSwitcher current={slug} />
	{#if hunt}
		<h1>{hunt.name}</h1>
		<p class="muted">{hunt.kind} · {hunt.role}</p>
	{:else if missing}
		<p class="muted">This hunt is not in your list.</p>
	{/if}
</main>

<style>
	main {
		min-height: 100vh;
		padding: 32px 48px;
		display: grid;
		align-content: start;
		gap: 16px;
	}

	h1 {
		font-family: var(--font-display);
		font-style: italic;
		font-weight: 560;
		margin: 0;
	}
</style>
