const STORAGE_KEY = 'researchPlannerSnapshot';

const isBrowser = () => typeof window !== 'undefined' && typeof sessionStorage !== 'undefined';

export const readResearchPlannerSnapshot = () => {
  if (!isBrowser()) {
    return null;
  }
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch (err) {
    console.warn('Failed to parse research planner snapshot', err);
    sessionStorage.removeItem(STORAGE_KEY);
  }
  return null;
};

export const writeResearchPlannerSnapshot = (snapshot) => {
  if (!isBrowser()) {
    return;
  }
  try {
    const payload = JSON.stringify(snapshot);
    sessionStorage.setItem(STORAGE_KEY, payload);
  } catch (err) {
    console.warn('Failed to store research planner snapshot', err);
  }
};

export const clearResearchPlannerSnapshot = () => {
  if (!isBrowser()) {
    return;
  }
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.warn('Failed to clear research planner snapshot', err);
  }
};
