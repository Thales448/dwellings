<script lang="ts">
	import { onMount } from 'svelte';
	import AuthSplit from '$lib/components/AuthSplit.svelte';
	import { api } from '$lib/api';
	import { credentialToJSON, requestOptions } from '$lib/auth';

	let email = $state('');
	let password = $state('');
	let trust = $state(false);
	let error = $state('');

	onMount(() => {
		void signInWithPasskey('conditional');
	});

	async function signInWithPasskey(mediation: CredentialMediationRequirement) {
		error = '';
		try {
			const issued = await api('/api/v1/auth/passkey/options', { method: 'POST', body: {} });
			if (!issued.ok) return;
			const payload = (await issued.json()) as {
				challenge_id: string;
				options: Parameters<typeof requestOptions>[0];
			};
			const credential = await navigator.credentials.get({
				mediation,
				publicKey: requestOptions(payload.options)
			});
			if (!credential) return;
			const verified = await api('/api/v1/auth/passkey/verify', {
				method: 'POST',
				body: { challenge_id: payload.challenge_id, credential: credentialToJSON(credential) }
			});
			if (verified.ok) window.location.href = '/';
		} catch {
			if (mediation !== 'conditional') error = 'Passkey sign-in was cancelled.';
		}
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		const response = await api('/api/v1/auth/password/login', {
			method: 'POST',
			body: { email, password, trust_device: trust }
		});
		const payload = (await response.json()) as { detail?: string; code?: string };
		if (payload.code === 'step_up_needed') {
			error = 'This account needs a passkey to finish signing in.';
			return;
		}
		if (!response.ok) {
			error = payload.detail ?? 'Could not sign in.';
			return;
		}
		window.location.href = '/';
	}
</script>

<AuthSplit>
	<p class="wordmark">Dwellings</p>
	<h1>Sign in</h1>
	<button class="btn primary" type="button" onclick={() => signInWithPasskey('required')}>
		Sign in with a passkey
	</button>
	<form onsubmit={submit}>
		<label>
			Email
			<input bind:value={email} type="email" autocomplete="username webauthn" required />
		</label>
		<label>
			Password
			<input bind:value={password} type="password" autocomplete="current-password" required />
		</label>
		<label class="check">
			<input bind:checked={trust} type="checkbox" />
			Trust this device for 30 days
		</label>
		{#if error}
			<p class="danger" role="alert">{error}</p>
		{/if}
		<button class="btn" type="submit">Sign in</button>
	</form>
</AuthSplit>

<style>
	h1 {
		font-size: 1.4rem;
		font-weight: 560;
		margin: 0;
	}

	form {
		display: grid;
		gap: 14px;
	}

	label {
		display: grid;
		gap: 6px;
		color: var(--muted);
	}

	input[type='email'],
	input[type='password'] {
		min-height: 44px;
		border: 1px solid var(--line);
		background: var(--raised);
		border-radius: 8px;
		padding: 0 12px;
	}

	.check {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 44px;
	}

	.btn {
		border: 0;
		border-radius: 999px;
		background: var(--raised);
		padding: 0 18px;
		cursor: pointer;
	}

	.primary {
		background: var(--love);
		color: var(--ground);
	}

	.primary:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.danger {
		color: var(--danger-text);
		margin: 0;
	}
</style>
