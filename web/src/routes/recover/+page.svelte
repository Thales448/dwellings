<script lang="ts">
	import { page } from '$app/stores';
	import AuthSplit from '$lib/components/AuthSplit.svelte';
	import { api } from '$lib/api';

	let token = $derived($page.url.searchParams.get('token') ?? '');
	let password = $state('');
	let error = $state('');
	let done = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		const response = await api('/api/v1/auth/recovery', {
			method: 'POST',
			body: { token, password }
		});
		const payload = (await response.json()) as { detail?: string };
		if (!response.ok) {
			error = payload.detail ?? 'This link is not valid.';
			return;
		}
		done = true;
	}
</script>

<AuthSplit>
	<p class="wordmark">Dwellings</p>
	<h1>Choose a new password</h1>
	{#if done}
		<p>Password updated. <a href="/login">Sign in</a></p>
	{:else}
		<form onsubmit={submit}>
			<label>
				New password
				<input bind:value={password} type="password" autocomplete="new-password" required />
			</label>
			{#if error}
				<p class="danger" role="alert">{error}</p>
			{/if}
			<button class="btn" type="submit">Update password</button>
		</form>
	{/if}
</AuthSplit>

<style>
	h1 {
		margin: 0;
		font-size: 1.4rem;
	}

	form,
	label {
		display: grid;
		gap: 8px;
	}

	form {
		gap: 14px;
	}

	label {
		color: var(--muted);
	}

	input {
		min-height: 44px;
		border: 1px solid var(--line);
		background: var(--raised);
		border-radius: 8px;
		padding: 0 12px;
	}

	.btn {
		border: 0;
		border-radius: 999px;
		background: var(--love);
		color: var(--ground);
	}

	.danger {
		color: var(--danger-text);
		margin: 0;
	}

	a {
		color: var(--love);
	}
</style>
