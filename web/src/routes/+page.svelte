<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { Hunt } from '$lib/listing';

	let signedOut = $state(false);

	onMount(() => {
		void enter();
	});

	async function enter() {
		const response = await api('/api/v1/hunts');
		if (!response.ok) {
			signedOut = true;
			return;
		}
		const hunts = ((await response.json()) as { hunts: Hunt[] }).hunts;
		if (hunts[0]) window.location.href = `/h/${hunts[0].slug}`;
		else signedOut = true;
	}
</script>

<main>
	<p class="wordmark">Dwellings</p>
	{#if signedOut}
		<p class="muted">Every place your agent finds, in one scroll.</p>
		<a class="enter" href="/login">Sign in</a>
	{:else}
		<p class="muted">Opening your hunt…</p>
	{/if}
</main>

<style>
	main {
		min-height: 100vh;
		display: grid;
		align-content: center;
		justify-items: start;
		padding: 48px;
		gap: 16px;
		background: var(--ground);
	}

	.enter {
		min-height: 44px;
		display: inline-flex;
		align-items: center;
		padding: 0 18px;
		border-radius: 999px;
		text-decoration: none;
		background: var(--love);
		color: var(--ground);
	}
</style>
