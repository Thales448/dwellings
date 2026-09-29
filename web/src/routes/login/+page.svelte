<script lang="ts">
	import { onMount } from 'svelte';
	import PlaceArt from '$lib/components/PlaceArt.svelte';
	import { api } from '$lib/api';
	import { credentialToJSON, requestOptions } from '$lib/auth';

	let email = $state('');
	let password = $state('');
	let trust = $state(true);
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

<div class="split">
	<div class="art">
		<PlaceArt />
		<div class="tagline">
			<span class="word">Dwellings</span>
			<span class="line">Every place your agent finds, in one scroll.</span>
		</div>
	</div>
	<div class="panel">
		<div>
			<h1>Welcome back</h1>
			<p class="lede">Sign in on this device with a passkey, or use your password.</p>
		</div>
		<button class="passkey" type="button" onclick={() => signInWithPasskey('required')}>
			Sign in with a passkey
		</button>
		<span class="hint">Face ID, Touch ID, Windows Hello or a security key</span>
		<div class="or"><span></span>or<span></span></div>
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
			<button class="password" type="submit">Sign in with password</button>
		</form>
		<p class="note">
			After a password sign-in you can add a passkey from Settings. Agents don't sign in here — they
			connect with a pairing code.
		</p>
	</div>
</div>

<style>
	.split {
		min-height: 100vh;
		display: grid;
		grid-template-columns: minmax(0, 1fr) 560px;
		background: var(--ground);
	}

	.art {
		position: relative;
		overflow: hidden;
		background: #3a3129;
	}

	.tagline {
		position: absolute;
		left: 56px;
		right: 56px;
		bottom: 56px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.word {
		font-family: var(--font-display);
		font-style: italic;
		font-size: 34px;
	}

	.line {
		font-family: var(--font-display);
		font-size: 52px;
		line-height: 1.05;
		letter-spacing: -1px;
		max-width: 640px;
	}

	.panel {
		padding: 0 72px;
		display: flex;
		flex-direction: column;
		justify-content: center;
		gap: 26px;
	}

	h1 {
		margin: 0;
		font-family: var(--font-display);
		font-weight: 400;
		font-size: 38px;
	}

	.lede,
	.hint,
	.note {
		margin: 8px 0 0;
		color: var(--muted);
		font-size: 15px;
		line-height: 1.5;
	}

	.hint,
	.note {
		font-size: 13px;
	}

	.passkey,
	.password {
		height: 56px;
		border-radius: 12px;
		border: 0;
		cursor: pointer;
		font-weight: 600;
	}

	.passkey {
		background: var(--text);
		color: var(--ground);
	}

	.password {
		height: 50px;
		border: 1px solid var(--line);
		background: transparent;
	}

	.or {
		display: flex;
		align-items: center;
		gap: 14px;
		color: #6f6a61;
		font-size: 13px;
	}

	.or span {
		flex: 1;
		height: 1px;
		background: var(--line);
	}

	form,
	label {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	label {
		gap: 6px;
		font-size: 13px;
		color: #d6d1c7;
	}

	input[type='email'],
	input[type='password'] {
		height: 48px;
		padding: 0 14px;
		border-radius: 10px;
		border: 1px solid var(--line);
		background: var(--surface);
	}

	.check {
		flex-direction: row;
		align-items: center;
		gap: 10px;
		font-size: 14px;
	}

	.danger {
		color: var(--danger-text);
		margin: 0;
	}

	@media (max-width: 900px) {
		.split {
			grid-template-columns: 1fr;
		}

		.art {
			min-height: 280px;
		}

		.line {
			font-size: 32px;
		}

		.panel {
			padding: 32px 24px 48px;
		}
	}
</style>
