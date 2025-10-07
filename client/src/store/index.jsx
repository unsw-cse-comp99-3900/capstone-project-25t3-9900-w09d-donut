import { createContext, useContext, useReducer } from "react";

const initialState = {
  preferences: null,
  activeRequestId: null,
  draft: null
};

const AppStateContext = createContext(initialState);
const AppDispatchContext = createContext(() => undefined);

const reducer = (state, action) => {
  // TODO: Extend reducer with domain-specific actions
  switch (action.type) {
    default:
      return state;
  }
};

export const AppStoreProvider = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  // TODO: Insert side effects such as persistence or analytics here

  return (
    <AppStateContext.Provider value={state}>
      <AppDispatchContext.Provider value={dispatch}>
        {children}
      </AppDispatchContext.Provider>
    </AppStateContext.Provider>
  );
};

export const useAppState = () => useContext(AppStateContext);
export const useAppDispatch = () => useContext(AppDispatchContext);
