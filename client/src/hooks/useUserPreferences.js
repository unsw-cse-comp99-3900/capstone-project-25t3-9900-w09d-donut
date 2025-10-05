import { useState } from "react";

export const useUserPreferences = () => {
  const [preferences, setPreferences] = useState(null);

  // TODO: Replace local state with global store integration
  // TODO: Persist preferences to the backend via dedicated service

  return {
    preferences,
    setPreferences
  };
};
