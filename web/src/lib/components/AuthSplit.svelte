<script lang="ts">
	let { children } = $props();
</script>

<div class="split">
	<section class="photo" aria-hidden="true">
		<p class="wordmark">Dwellings</p>
		<p>Late light on a Queens walk-up.</p>
	</section>
	<section class="pane">
		{@render children()}
	</section>
</div>

<style>
	.split {
		min-height: 100vh;
		display: grid;
		grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
	}

	.photo {
		background:
			linear-gradient(180deg, rgb(15 14 12 / 10%), rgb(15 14 12 / 72%)),
			radial-gradient(circle at 30% 20%, #8a5a3a, transparent 42%),
			radial-gradient(circle at 70% 80%, #3d4a38, transparent 40%),
			#221f1b;
		padding: 48px;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
		gap: 12px;
	}

	.photo p:last-child {
		margin: 0;
		color: var(--muted);
		max-width: 18rem;
	}

	.pane {
		background: var(--surface);
		padding: 48px 40px;
		display: grid;
		align-content: center;
		gap: 16px;
	}

	@media (max-width: 800px) {
		.split {
			grid-template-columns: 1fr;
		}

		.photo {
			min-height: 28vh;
		}
	}
</style>
