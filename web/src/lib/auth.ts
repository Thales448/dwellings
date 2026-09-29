type CredentialDescriptor = {
	id: string;
	type: PublicKeyCredentialType;
	transports?: AuthenticatorTransport[];
};

export function bytesFromBase64Url(value: string): ArrayBuffer {
	const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((value.length + 3) % 4);
	const binary = atob(padded);
	const bytes = new Uint8Array(binary.length);
	for (let index = 0; index < binary.length; index += 1) {
		bytes[index] = binary.charCodeAt(index);
	}
	return bytes.buffer;
}

export function requestOptions(options: {
	challenge: string;
	timeout?: number;
	rpId?: string;
	userVerification?: UserVerificationRequirement;
	allowCredentials?: CredentialDescriptor[];
}): PublicKeyCredentialRequestOptions {
	return {
		challenge: bytesFromBase64Url(options.challenge),
		timeout: options.timeout,
		rpId: options.rpId,
		userVerification: options.userVerification,
		allowCredentials: (options.allowCredentials ?? []).map((item) => ({
			type: item.type,
			id: bytesFromBase64Url(item.id),
			transports: item.transports
		}))
	};
}

export function creationOptions(options: {
	challenge: string;
	timeout?: number;
	rp: PublicKeyCredentialRpEntity;
	user: { id: string; name: string; displayName: string };
	pubKeyCredParams: PublicKeyCredentialParameters[];
	authenticatorSelection?: AuthenticatorSelectionCriteria;
	attestation?: AttestationConveyancePreference;
	excludeCredentials?: CredentialDescriptor[];
}): PublicKeyCredentialCreationOptions {
	return {
		challenge: bytesFromBase64Url(options.challenge),
		timeout: options.timeout,
		rp: options.rp,
		user: {
			id: bytesFromBase64Url(options.user.id),
			name: options.user.name,
			displayName: options.user.displayName
		},
		pubKeyCredParams: options.pubKeyCredParams,
		authenticatorSelection: options.authenticatorSelection,
		attestation: options.attestation,
		excludeCredentials: (options.excludeCredentials ?? []).map((item) => ({
			type: item.type,
			id: bytesFromBase64Url(item.id),
			transports: item.transports
		}))
	};
}

export function credentialToJSON(credential: Credential): unknown {
	if ('toJSON' in credential && typeof credential.toJSON === 'function') {
		return credential.toJSON();
	}
	throw new Error('This browser cannot serialize a passkey response.');
}
