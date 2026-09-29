<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { creationOptions, credentialToJSON } from '$lib/auth';
	import { seenLabel, type Hunt } from '$lib/listing';

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
	type AgentCard = {
		id: string;
		name: string;
		scopes: string[];
		last_seen_at: string | null;
		revoked_at: string | null;
		posts: number;
	};
	type Member = {
		user_id: string;
		display_name: string;
		role: string;
		email: string;
	};

	let hunts = $state<Hunt[]>([]);
	let selected = $state<Hunt | null>(null);
	let agents = $state<AgentCard[]>([]);
	let members = $state<Member[]>([]);
	let credentials = $state<CredentialCard[]>([]);
	let sessions = $state<SessionCard[]>([]);
	let nickname = $state('This device');
	let error = $state('');
	let code = $state('');
	let expiresAt = $state('');
	let remaining = $state('');
	let inviteToken = $state('');
	let pane = $state<'hunt' | 'devices'>('hunt');

	onMount(() => {
		void refresh();
		const timer = setInterval(tick, 1000);
		return () => clearInterval(timer);
	});

	function tick() {
		if (!expiresAt) {
			remaining = '';
			return;
		}
		const left = new Date(expiresAt).getTime() - Date.now();
		if (left <= 0) {
			remaining = 'expired';
			return;
		}
		const minutes = Math.floor(left / 60000);
		const seconds = Math.floor((left % 60000) / 1000);
		remaining = `${minutes}:${String(seconds).padStart(2, '0')}`;
	}

	async function refresh() {
		const [huntResponse, credentialResponse, sessionResponse] = await Promise.all([
			api('/api/v1/hunts'),
			api('/api/v1/auth/credentials'),
			api('/api/v1/auth/sessions')
		]);
		if (!huntResponse.ok) {
			window.location.href = '/login';
			return;
		}
		hunts = ((await huntResponse.json()) as { hunts: Hunt[] }).hunts;
		if (!selected && hunts[0]) selected = hunts[0];
		if (credentialResponse.ok) {
			credentials = ((await credentialResponse.json()) as { credentials: CredentialCard[] })
				.credentials;
		}
		if (sessionResponse.ok) {
			sessions = ((await sessionResponse.json()) as { sessions: SessionCard[] }).sessions;
		}
		if (selected) await loadHunt(selected);
	}

	async function loadHunt(hunt: Hunt) {
		selected = hunt;
		pane = 'hunt';
		const [agentResponse, memberResponse] = await Promise.all([
			api(`/api/v1/hunts/${hunt.id}/agents`),
			api(`/api/v1/hunts/${hunt.id}/members`)
		]);
		agents = agentResponse.ok
			? ((await agentResponse.json()) as { agents: AgentCard[] }).agents
			: [];
		members = memberResponse.ok
			? ((await memberResponse.json()) as { members: Member[] }).members
			: [];
	}

	function chips(criteria: Record<string, unknown>): string[] {
		return Object.entries(criteria).map(([key, value]) => {
			if (Array.isArray(value)) return `${key} ${value.join(' · ')}`;
			return `${key} ${value}`;
		});
	}

	async function connect() {
		if (!selected) return;
		error = '';
		const response = await api(`/api/v1/hunts/${selected.id}/pairing-codes`, {
			method: 'POST',
			body: {}
		});
		if (!response.ok) {
			error = 'Could not create a pairing code.';
			return;
		}
		const payload = (await response.json()) as { code: string; expires_at: string };
		code = payload.code;
		expiresAt = payload.expires_at;
		tick();
	}

	async function revoke(agentId: string) {
		if (!selected) return;
		error = '';
		const response = await api(`/api/v1/hunts/${selected.id}/agents/${agentId}`, {
			method: 'DELETE'
		});
		if (!response.ok) {
			error = 'Could not revoke that agent.';
			return;
		}
		await loadHunt(selected);
	}

	async function invite() {
		if (!selected) return;
		error = '';
		const response = await api(`/api/v1/hunts/${selected.id}/invites`, {
			method: 'POST',
			body: { role: 'rater' }
		});
		if (!response.ok) {
			error = 'Could not create an invite. Owners need a recent sign-in.';
			return;
		}
		inviteToken = ((await response.json()) as { token: string }).token;
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
		await api('/api/v1/auth/sessions/revoke-others', { method: 'POST', body: {} });
		await refresh();
	}
</script>

<div class="screen">
	<header>
		<a class="wordmark" href={selected ? `/h/${selected.slug}` : '/'}>Dwellings</a>
		<a class="back" href={selected ? `/h/${selected.slug}` : '/'}>Back to feed</a>
	</header>
	<div class="body">
		<nav>
			<span class="kicker">Your hunts</span>
			{#each hunts as hunt (hunt.id)}
				<button type="button" class:on={selected?.id === hunt.id} onclick={() => loadHunt(hunt)}>
					<span>{hunt.name}</span>
					<span class="sub">{hunt.kind} · {hunt.role}</span>
				</button>
			{/each}
			<span class="kicker account">Account</span>
			<button type="button" class:on={pane === 'devices'} onclick={() => (pane = 'devices')}>
				Devices & passkeys
			</button>
		</nav>
		<main>
			{#if error}
				<p class="danger" role="alert">{error}</p>
			{/if}
			{#if pane === 'hunt' && selected}
				<section class="head">
					<div>
						<span class="kicker">Hunt</span>
						<h1>{selected.name}</h1>
					</div>
					<div class="chips">
						{#each chips(selected.criteria) as chip (chip)}
							<span>{chip}</span>
						{/each}
					</div>
				</section>
				<section class="card">
					<div class="row">
						<h2>Agents</h2>
						<button class="solid" type="button" onclick={connect}>Connect an agent</button>
					</div>
					{#each agents as agent (agent.id)}
						<div class="agent">
							<span class="dot" class:off={agent.revoked_at}></span>
							<div class="grow">
								<span class="mono">{agent.name}</span>
								<span class="sub">{agent.scopes.join(' · ')}</span>
							</div>
							<span class="sub">
								{agent.posts} posts · {agent.last_seen_at ? `seen ${seenLabel(agent.last_seen_at)}` : 'never seen'}
							</span>
							{#if !agent.revoked_at}
								<button type="button" onclick={() => revoke(agent.id)}>Revoke</button>
							{/if}
						</div>
					{/each}
					{#if code}
						<div class="pair">
							<span class="kicker">Pairing code · expires in {remaining}</span>
							<span class="code">{code}</span>
							<code>POST /api/v1/agents/pair
{`{ "code": "${code}", "name": "hunt-agent" }`}
→ scoped token and MCP URL, shown once</code>
						</div>
					{/if}
				</section>
				<section class="card">
					<h2>Members</h2>
					{#each members as member (member.user_id)}
						<div class="member">
							<span class="avatar">{member.display_name.slice(0, 1).toUpperCase()}</span>
							<span class="grow">{member.display_name}</span>
							<span class="sub">{member.role}</span>
						</div>
					{/each}
					<button type="button" onclick={invite}>Invite by link</button>
					{#if inviteToken}
						<p class="sub">
							Give this token once. The invitee accepts it at
							<code>POST /api/v1/auth/invite/accept</code>.
						</p>
						<span class="code small">{inviteToken}</span>
					{/if}
					<div class="learned">
						<span class="kicker">What the agent has learned</span>
						<p>Learning arrives in a later pass. Ratings on the feed stay on this device for now.</p>
					</div>
				</section>
			{/if}
			<section class="card wide" class:hidden={pane !== 'devices' && pane !== 'hunt'}>
				<div class="row">
					<h2>Your devices & passkeys</h2>
					<button class="love" type="button" onclick={addPasskey}>Add a passkey</button>
				</div>
				<label>
					Nickname
					<input bind:value={nickname} />
				</label>
				<div class="devices">
					{#each credentials as credential (credential.id)}
						<article>
							<strong>{credential.nickname}</strong>
							<span class="sub">Passkey · {credential.last_used_at ? `used ${seenLabel(credential.last_used_at)}` : 'not used yet'}</span>
							<button type="button" onclick={() => removeCredential(credential.id)}>Remove</button>
						</article>
					{/each}
					{#each sessions as session (session.id)}
						<article>
							<strong>{session.device_label}</strong>
							<span class="sub">{session.auth_method}{#if session.current} · this device{/if}</span>
							<span class="sub">{session.trusted_until ? `Trusted until ${session.trusted_until}` : 'Session'}</span>
						</article>
					{/each}
					<article>
						<strong>Password</strong>
						<span class="sub">Other sessions stay signed in until you revoke them.</span>
						<button type="button" onclick={signOutAll}>Sign out other sessions</button>
					</article>
				</div>
			</section>
		</main>
	</div>
</div>

<style>
	.screen {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		background: var(--ground);
	}

	header {
		height: 72px;
		padding: 0 32px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid var(--line);
	}

	.wordmark {
		font-family: var(--font-display);
		font-style: italic;
		font-size: 30px;
		text-decoration: none;
	}

	.back {
		padding: 10px 16px;
		border: 1px solid var(--line);
		border-radius: 999px;
		text-decoration: none;
	}

	.body {
		flex: 1;
		display: grid;
		grid-template-columns: 280px minmax(0, 1fr);
	}

	nav {
		border-right: 1px solid var(--line);
		padding: 24px 16px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.kicker {
		padding: 0 12px 8px;
		font-size: 12px;
		letter-spacing: 1.6px;
		text-transform: uppercase;
		color: var(--muted);
	}

	.account {
		padding-top: 24px;
	}

	nav button,
	.card button,
	.love,
	.solid {
		border: 0;
		background: transparent;
		color: inherit;
		text-align: left;
		cursor: pointer;
		border-radius: 10px;
		padding: 12px;
	}

	nav button {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	nav button.on {
		background: var(--raised);
	}

	.sub {
		font-size: 12px;
		color: var(--muted);
	}

	main {
		padding: 32px 40px;
		display: grid;
		grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
		gap: 28px;
		align-content: start;
	}

	.head,
	.wide {
		grid-column: 1 / span 2;
	}

	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
	}

	h1 {
		margin: 8px 0 0;
		font-family: var(--font-display);
		font-weight: 400;
		font-size: 44px;
	}

	h2 {
		margin: 0;
		font-size: 18px;
	}

	.chips {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		justify-content: flex-end;
		max-width: 620px;
	}

	.chips span {
		padding: 6px 12px;
		border: 1px solid var(--line);
		border-radius: 999px;
		font-family: var(--font-mono);
		font-size: 12px;
	}

	.card {
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 22px;
		border: 1px solid var(--line);
		border-radius: 16px;
		background: #141311;
	}

	.row,
	.agent,
	.member {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.row {
		justify-content: space-between;
	}

	.solid {
		background: var(--text);
		color: var(--ground);
		font-weight: 600;
		border-radius: 999px;
		padding: 0 16px;
	}

	.love {
		border: 1px solid var(--love);
		color: var(--love);
		border-radius: 999px;
		padding: 0 16px;
		font-weight: 600;
	}

	.agent,
	.member {
		padding: 10px 0;
		border-bottom: 1px solid #1f1e1b;
	}

	.grow {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	.dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--ok);
		box-shadow: 0 0 0 4px rgba(143, 185, 150, 0.18);
	}

	.dot.off {
		background: var(--muted);
		box-shadow: none;
	}

	.mono,
	.code,
	code {
		font-family: var(--font-mono);
	}

	.pair {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 18px;
		border-radius: 12px;
		border: 1px dashed #3a3833;
	}

	.code {
		font-size: 34px;
		letter-spacing: 3px;
		word-break: break-all;
	}

	.code.small {
		font-size: 14px;
		letter-spacing: 0;
	}

	code {
		font-size: 12px;
		line-height: 1.6;
		color: #d6d1c7;
		white-space: pre-line;
	}

	.avatar {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		background: #2f2b36;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 600;
	}

	.learned p,
	.danger {
		margin: 0;
	}

	.learned p {
		font-family: var(--font-display);
		font-size: 17px;
		line-height: 1.45;
	}

	.danger {
		color: var(--danger-text);
		grid-column: 1 / span 2;
	}

	.devices {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 12px;
	}

	article {
		padding: 16px;
		border-radius: 12px;
		background: var(--surface);
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	label {
		display: grid;
		gap: 6px;
		color: var(--muted);
		font-size: 13px;
	}

	input {
		min-height: 44px;
		border: 1px solid var(--line);
		background: var(--raised);
		border-radius: 8px;
		padding: 0 12px;
	}

	.hidden {
		display: none;
	}

	@media (max-width: 1000px) {
		.body,
		main,
		.devices {
			grid-template-columns: 1fr;
		}

		.head,
		.wide,
		.danger {
			grid-column: auto;
		}
	}
</style>
