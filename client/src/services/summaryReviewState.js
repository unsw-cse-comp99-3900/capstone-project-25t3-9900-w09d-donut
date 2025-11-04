const STORAGE_KEY = 'summaryReviewPageSnapshot';

const isBrowser = () => typeof window !== 'undefined' && typeof sessionStorage !== 'undefined';

export const readSummaryReviewSnapshot = () => {
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
    console.warn('Failed to parse summary review snapshot', err);
    sessionStorage.removeItem(STORAGE_KEY);
  }
  return null;
};

export const writeSummaryReviewSnapshot = (snapshot) => {
  if (!isBrowser()) {
    return;
  }
  try {
    const payload = JSON.stringify(snapshot);
    sessionStorage.setItem(STORAGE_KEY, payload);
  } catch (err) {
    console.warn('Failed to store summary review snapshot', err);
  }
};

export const clearSummaryReviewSnapshot = () => {
  if (!isBrowser()) {
    return;
  }
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.warn('Failed to clear summary review snapshot', err);
  }
};
