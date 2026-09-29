<script lang="ts">
	import { page } from '$app/stores';
	import AuthSplit from '$lib/components/AuthSplit.svelte';
	import { api } from '$lib/api';

	let token = $derived($page.url.searchParams.get('token') ?? '');
	let email = $state('');
	let displayName = $state('');
	let password = $state('');
	let error = $state('');

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		const response = await api('/api/v1/setup', {
			method: 'POST',
			body: { token, email, password, display_name: displayName }
		});
		const payload = (await response.json()) as { detail?: string };
		if (!response.ok) {
			error = payload.detail ?? 'Setup failed.';
			return;
		}
		window.location.href = '/';
	}
</script>

<AuthSplit>
	<p class="wordmark">Dwellings</p>
	<h1>Create the admin</h1>
	<form onsubmit={submit}>
		<label>
			Email
			<input bind:value={email} type="email" autocomplete="username" required />
		</label>
		<label>
			Name
			<input bind:value={displayName} autocomplete="name" required />
		</label>
		<label>
			Password
			<input bind:value={password} type="password" autocomplete="new-password" required />
		</label>
		{#if error}
			<p class="danger" role="alert">{error}</p>
		{/if}
		<button class="btn" type="submit">Create account</button>
	</form>
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
		min-height: 44px;
		border: 0;
		border-radius: 999px;
		background: var(--love);
		color: var(--ground);
	}

	.danger {
		color: var(--danger-text);
		margin: 0;
	}
</style>
