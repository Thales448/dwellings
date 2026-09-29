<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { creationOptions, credentialToJSON } from '$lib/auth';

	type CredentialCard = {
		id: string;
		nickname: string;
		created_at: string;
		last_used_at: string | null;
	};
	type SessionCard = {
		id: string;
		device_label: string;
		auth_method: string;
		current: boolean;
		trusted_until: string | null;
		last_seen_at: string;
	};

	let credentials = $state<CredentialCard[]>([]);
	let sessions = $state<SessionCard[]>([]);
	let nickname = $state('This device');
	let error = $state('');

	onMount(() => {
		void refresh();
	});

	async function refresh() {
		const [credentialResponse, sessionResponse] = await Promise.all([
			api('/api/v1/auth/credentials'),
			api('/api/v1/auth/sessions')
		]);
		if (credentialResponse.ok) {
			credentials = ((await credentialResponse.json()) as { credentials: CredentialCard[] }).credentials;
		}
		if (sessionResponse.ok) {
			sessions = ((await sessionResponse.json()) as { sessions: SessionCard[] }).sessions;
		}
	}

	async function addPasskey() {
		error = '';
		const issued = await api('/api/v1/auth/passkey/register/options', { method: 'POST', body: {} });
		if (!issued.ok) {
			error = 'Sign in again to add a passkey.';
			return;
		}
		const payload = (await issued.json()) as {
			challenge_id: string;
			options: Parameters<typeof creationOptions>[0];
		};
		const credential = await navigator.credentials.create({
			publicKey: creationOptions(payload.options)
		});
		if (!credential) return;
		const saved = await api('/api/v1/auth/passkey/register/verify', {
			method: 'POST',
			body: {
				challenge_id: payload.challenge_id,
				credential: credentialToJSON(credential),
				nickname
			}
		});
		if (!saved.ok) {
			error = 'Could not save this passkey.';
			return;
		}
		await refresh();
	}

	async function removeCredential(id: string) {
		error = '';
		const response = await api(`/api/v1/auth/credentials/${id}`, { method: 'DELETE' });
		if (!response.ok) {
			const payload = (await response.json()) as { detail?: string };
			error = payload.detail ?? 'Could not remove the passkey.';
			return;
		}
		await refresh();
	}

	async function signOutAll() {
		await api('/api/v1/auth/sessions/revoke-all', { method: 'POST', body: {} });
		window.location.href = '/login';
	}
</script>

<main>
	<p class="wordmark">Dwellings</p>
	<h1>Devices and passkeys</h1>
	{#if error}
		<p class="danger" role="alert">{error}</p>
	{/if}

	<section>
		<h2>Passkeys</h2>
		{#each credentials as credential (credential.id)}
			<article class="card">
				<strong>{credential.nickname}</strong>
				<p class="muted mono">{credential.id.slice(0, 12)}</p>
				<button type="button" onclick={() => removeCredential(credential.id)}>Remove</button>
			</article>
		{/each}
		<label>
			Nickname
			<input bind:value={nickname} />
		</label>
		<button class="primary" type="button" onclick={addPasskey}>Add a passkey</button>
	</section>

	<section>
		<h2>Sessions</h2>
		{#each sessions as session (session.id)}
			<article class="card">
				<strong>{session.device_label}</strong>
				<p class="muted">
					{session.auth_method}
					{#if session.current}· this device{/if}
					{#if session.trusted_until}· trusted until {session.trusted_until}{/if}
				</p>
			</article>
		{/each}
		<button type="button" onclick={signOutAll}>Sign out all sessions</button>
	</section>
</main>

<style>
	main {
		min-height: 100vh;
		padding: 48px;
		display: grid;
		align-content: start;
		gap: 24px;
		max-width: 720px;
	}

	h1,
	h2 {
		margin: 0;
		font-weight: 560;
	}

	section {
		display: grid;
		gap: 12px;
	}

	.card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 16px;
		display: grid;
		gap: 6px;
	}

	label {
		display: grid;
		gap: 6px;
		color: var(--muted);
	}

	input {
		min-height: 44px;
		border: 1px solid var(--line);
		background: var(--raised);
		border-radius: 8px;
		padding: 0 12px;
	}

	button {
		border: 0;
		border-radius: 999px;
		background: var(--raised);
		padding: 0 16px;
	}

	.primary {
		background: var(--love);
		color: var(--ground);
	}

	.danger {
		color: var(--danger-text);
		margin: 0;
	}
</style>
