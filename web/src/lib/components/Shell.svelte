<script lang="ts">
	import type { Hunt } from '$lib/listing';

	let {
		slug,
		huntName,
		hunts,
		active,
		unrated = 0,
		pulse = 'no heartbeat yet'
	}: {
		slug: string;
		huntName: string;
		hunts: Hunt[];
		active: 'feed' | 'wall' | 'gone';
		unrated?: number;
		pulse?: string;
	} = $props();
</script>

<header>
	<div class="brand">
		<a class="wordmark" href="/">Dwellings</a>
		<details>
			<summary>
				<span class="kicker">Hunt</span>
				<span class="name">{huntName}</span>
				<svg viewBox="0 0 24 24" width="16" height="16"><path d="M6 9l6 6 6-6" /></svg>
			</summary>
			<div class="menu">
				{#each hunts as hunt (hunt.slug)}
					<a href="/h/{hunt.slug}">{hunt.name}</a>
				{/each}
			</div>
		</details>
	</div>
	<nav>
		<a class:on={active === 'feed'} href="/h/{slug}">Feed</a>
		<a class:on={active === 'wall'} href="/h/{slug}/wall">Wall</a>
		<a href="/h/{slug}/wall?filter=tour">Tours</a>
		<a class:on={active === 'gone'} class:quiet={active !== 'gone'} href="/h/{slug}/wall?filter=gone">Gone</a>
	</nav>
	<div class="tools">
		<div class="pulse">
			<span class="dot"></span>
			<span>{pulse}</span>
		</div>
		<div class="count"><span>{unrated}</span> unrated</div>
		<a class="avatar" href="/settings" aria-label="Settings">O</a>
	</div>
</header>

<style>
	header {
		height: 72px;
		box-sizing: border-box;
		padding: 0 32px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid var(--line);
		gap: 16px;
	}

	.brand,
	.tools,
	.pulse {
		display: flex;
		align-items: center;
		gap: 14px;
	}

	.wordmark {
		font-family: var(--font-display);
		font-style: italic;
		font-size: 30px;
		letter-spacing: -0.5px;
		text-decoration: none;
	}

	summary {
		height: 40px;
		padding: 0 14px;
		border-radius: 10px;
		border: 1px solid var(--line);
		background: var(--surface);
		list-style: none;
		display: flex;
		align-items: center;
		gap: 10px;
		cursor: pointer;
	}

	summary::-webkit-details-marker {
		display: none;
	}

	.kicker {
		font-size: 11px;
		letter-spacing: 1.4px;
		text-transform: uppercase;
		color: var(--muted);
	}

	.name {
		font-weight: 600;
	}

	svg {
		fill: none;
		stroke: currentColor;
		stroke-width: 1.8;
	}

	details {
		position: relative;
	}

	.menu {
		position: absolute;
		top: 46px;
		left: 0;
		min-width: 220px;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 6px;
		display: grid;
		z-index: 2;
	}

	.menu a {
		padding: 10px 12px;
		border-radius: 8px;
		text-decoration: none;
	}

	nav {
		display: flex;
		gap: 4px;
		padding: 4px;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 999px;
	}

	nav a {
		padding: 10px 18px;
		border-radius: 999px;
		text-decoration: none;
		font-size: 14px;
	}

	nav a.on {
		background: var(--text);
		color: var(--ground);
		font-weight: 600;
	}

	.quiet {
		color: var(--muted);
	}

	.pulse {
		padding: 8px 14px;
		border: 1px solid var(--line);
		border-radius: 999px;
		font-size: 13px;
	}

	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--ok);
		box-shadow: 0 0 0 4px rgba(143, 185, 150, 0.18);
	}

	.count {
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--muted);
	}

	.count span {
		color: var(--text);
	}

	.avatar {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: #2f2b36;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 14px;
		font-weight: 600;
		text-decoration: none;
	}
</style>
