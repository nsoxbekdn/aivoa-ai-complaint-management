import { configureStore } from '@reduxjs/toolkit';

import complaintsReducer, {
  initialComplaintsState,
  type ComplaintsState,
} from '../features/complaints/complaintsSlice';

const STORAGE_KEY = 'aivoa.intake.v1';

/** Only the in-progress complaint. Server lists, the open record and every loading flag are
 *  refetched or reset on load, and persisting them would restore a stale or mid-flight view. */
type PersistedIntake = Pick<
  ComplaintsState,
  'formData' | 'fieldSources' | 'analysis' | 'intakeChat' | 'pastedText'
>;

function loadIntake(): { complaints: ComplaintsState } | undefined {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (!stored) return undefined;
    const intake = JSON.parse(stored) as PersistedIntake;
    return {
      // Spread over the full initial state, never in place of it: server lists, the open
      // record and every loading flag must start fresh, and a missing one would be undefined.
      complaints: {
        ...initialComplaintsState,
        ...intake,
        // A request cannot survive the reload that killed it.
        intakeChat: { ...intake.intakeChat, pending: false, error: null, failed: null },
      },
    };
  } catch {
    // Corrupt or unavailable storage must never stop the app from starting.
    return undefined;
  }
}

export const store = configureStore({
  reducer: {
    complaints: complaintsReducer,
  },
  preloadedState: loadIntake(),
});

let lastSaved: PersistedIntake | null = null;

store.subscribe(() => {
  const { formData, fieldSources, analysis, intakeChat, pastedText } = store.getState().complaints;
  // Reference equality is enough: the reducers are immutable, so an unchanged slice keeps
  // the same objects and this skips a JSON.stringify on every unrelated dispatch.
  if (
    lastSaved &&
    lastSaved.formData === formData &&
    lastSaved.analysis === analysis &&
    lastSaved.intakeChat === intakeChat
  ) {
    return;
  }
  lastSaved = { formData, fieldSources, analysis, intakeChat, pastedText };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(lastSaved));
  } catch {
    // Private-browsing quota failures are not worth interrupting intake for.
  }
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
