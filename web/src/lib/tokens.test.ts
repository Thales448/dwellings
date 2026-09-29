import { describe, expect, it } from 'vitest';
import { tokens } from './tokens';

describe('design tokens', () => {
	it('matches the plan palette and typefaces', () => {
		expect(tokens.ground).toBe('#0f0e0c');
		expect(tokens.love).toBe('#e8845c');
		expect(tokens.danger).toBe('#e5484d');
		expect(tokens.fontDisplay).toBe('Fraunces');
		expect(tokens.fontUi).toBe('Instrument Sans');
		expect(tokens.fontMono).toBe('JetBrains Mono');
	});
});
