export type Mark = {
	stars?: number;
	tour?: string;
	tags?: string[];
};

const KEY = 'dwl-marks';

export function loadMarks(): Record<string, Mark> {
	try {
		const raw = sessionStorage.getItem(KEY);
		if (!raw) return {};
		const parsed = JSON.parse(raw) as Record<string, Mark>;
		return parsed && typeof parsed === 'object' ? parsed : {};
	} catch {
		return {};
	}
}

export function saveMarks(marks: Record<string, Mark>): void {
	sessionStorage.setItem(KEY, JSON.stringify(marks));
}
