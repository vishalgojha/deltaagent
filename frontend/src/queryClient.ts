import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { clearSession } from "./store/session";
import { isAuthError } from "./api/errors";

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      if (isAuthError(error)) clearSession();
    }
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      if (isAuthError(error)) clearSession();
    }
  }),
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: 1
    },
    mutations: {
      retry: 0
    }
  }
});
