<script lang="ts">
	import HuntSwitcher from '$lib/components/HuntSwitcher.svelte';
</script>

<main>
	<HuntSwitcher />
	<p class="wordmark">Dwellings</p>
	<p class="muted">Listing hunts, rated by the people who live with them.</p>
	<a class="enter" href="/login">Sign in</a>
	<a class="quiet" href="/settings">Devices</a>
</main>

<style>
	main {
		min-height: 100vh;
		display: grid;
		align-content: center;
		justify-items: start;
		padding: 48px;
		gap: 12px;
		background: var(--ground);
	}

	.enter,
	.quiet {
		min-height: 44px;
		display: inline-flex;
		align-items: center;
		padding: 0 18px;
		border-radius: 999px;
		text-decoration: none;
	}

	.enter {
		background: var(--love);
		color: var(--ground);
	}

	.quiet {
		color: var(--muted);
	}
</style>
