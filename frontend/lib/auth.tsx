"use client";

import {
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { config } from "./config";

interface AuthState {
  ready: boolean;
  signedIn: boolean;
  accountName: string | null;
  mockUser: string;
  setMockUser: (u: string) => void;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthState | null>(null);

let msal: PublicClientApplication | null = null;
function getMsal(): PublicClientApplication {
  if (!msal) {
    msal = new PublicClientApplication({
      auth: {
        clientId: config.clientId,
        authority: `https://login.microsoftonline.com/${config.tenantId}`,
        redirectUri: typeof window !== "undefined" ? window.location.origin : undefined,
      },
      // sessionStorage: tokens do not outlive the tab (plan §9)
      cache: { cacheLocation: "sessionStorage" },
    });
  }
  return msal;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(config.authMode === "mock");
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [mockUser, setMockUserState] = useState("dev-user");

  useEffect(() => {
    if (config.authMode === "mock") {
      try {
        const saved = sessionStorage.getItem("mockUser");
        if (saved) setMockUserState(saved);
      } catch {
        /* storage unavailable */
      }
      return;
    }
    const app = getMsal();
    app
      .initialize()
      .then(() => app.handleRedirectPromise())
      .then((result) => {
        const acc = result?.account ?? app.getAllAccounts()[0] ?? null;
        if (acc) app.setActiveAccount(acc);
        setAccount(acc);
      })
      .catch(() => setAccount(null))
      .finally(() => setReady(true));
  }, []);

  const setMockUser = useCallback((u: string) => {
    setMockUserState(u);
    try {
      sessionStorage.setItem("mockUser", u);
    } catch {
      /* ignore */
    }
  }, []);

  const signIn = useCallback(async () => {
    if (config.authMode === "mock") return;
    await getMsal().loginRedirect({ scopes: [config.apiScope] });
  }, []);

  const signOut = useCallback(async () => {
    if (config.authMode === "mock") return;
    await getMsal().logoutRedirect();
  }, []);

  const getToken = useCallback(async () => {
    if (config.authMode === "mock") return null;
    const app = getMsal();
    const acc = app.getActiveAccount();
    if (!acc) return null;
    try {
      const r = await app.acquireTokenSilent({ scopes: [config.apiScope], account: acc });
      return r.accessToken;
    } catch (e) {
      if (e instanceof InteractionRequiredAuthError) {
        await app.acquireTokenRedirect({ scopes: [config.apiScope] });
      }
      throw e;
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      ready,
      signedIn: config.authMode === "mock" || !!account,
      accountName: config.authMode === "mock" ? mockUser : account?.name ?? null,
      mockUser,
      setMockUser,
      signIn,
      signOut,
      getToken,
    }),
    [ready, account, mockUser, setMockUser, signIn, signOut, getToken],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
