"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  ApiError,
  clearTokens,
  getAccessToken,
  getMe,
  login as loginRequest,
  logout as logoutRequest,
  onAuthChange,
  registerAccount,
  storeTokens,
  type User,
} from "@/lib/api";

interface AuthState {
  user: User | null;
  /** True until the stored token has been checked, so guards do not flash. */
  loading: boolean;
  isAdmin: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  signUp: (email: string, password: string, fullName: string) => Promise<User>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Assigned inside the effect so the storage listener can re-resolve without
  // re-subscribing.
  const resolveRef = useRef<() => Promise<void>>(async () => {});

  /**
   * Resolve the session from whatever token is in storage.
   *
   * The token is not trusted on its face -- `/api/auth/me` is what decides who
   * the user is, so a tampered or stale token resolves to signed-out rather
   * than to a fake identity. The role that gates admin UI comes from the
   * server's answer, and the server re-checks it on every admin request anyway.
   */
  useEffect(() => {
    let cancelled = false;

    const resolve = async () => {
      let me: User | null = null;
      try {
        // Awaiting even the no-token case keeps every setState off the
        // synchronous effect path.
        me = await (getAccessToken() ? getMe() : Promise.resolve(null));
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) clearTokens();
      }
      if (cancelled) return;
      setUser(me);
      setLoading(false);
    };

    resolveRef.current = resolve;
    resolve();

    // Keep tabs in step: signing out in one window signs out the others.
    const unsubscribe = onAuthChange(() => {
      if (!getAccessToken()) setUser(null);
    });
    const onStorage = (event: StorageEvent) => {
      if (event.key?.startsWith("seatbook.")) resolveRef.current();
    };
    window.addEventListener("storage", onStorage);

    return () => {
      cancelled = true;
      unsubscribe();
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const session = await loginRequest({ email, password });
    storeTokens(session.tokens);
    setUser(session.user);
    return session.user;
  }, []);

  const signUp = useCallback(
    async (email: string, password: string, fullName: string) => {
      const session = await registerAccount({
        email,
        password,
        full_name: fullName,
      });
      storeTokens(session.tokens);
      setUser(session.user);
      return session.user;
    },
    [],
  );

  const signOut = useCallback(async () => {
    await logoutRequest();
    setUser(null);
  }, []);

  return (
    <AuthContext
      value={{
        user,
        loading,
        isAdmin: user?.role === "ADMIN",
        signIn,
        signUp,
        signOut,
      }}
    >
      {children}
    </AuthContext>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
