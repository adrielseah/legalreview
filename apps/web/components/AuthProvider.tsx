"use client";

import { createContext, useContext } from "react";
import { Loader2 } from "lucide-react";
import useAuth from "@/lib/useAuth";
import { LoginPage } from "@/components/LoginPage";

interface AuthContextValue {
  authToken: string | null;
  authUser: { userId: number; email: string; name: string; role: string } | null;
  isAdmin: boolean;
  authHeaders: () => Record<string, string>;
  handleLogout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  authToken: null,
  authUser: null,
  isAdmin: false,
  authHeaders: () => ({}),
  handleLogout: async () => {},
});

export function useAuthContext() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const auth = useAuth();

  if (auth.checkingAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!auth.authToken || !auth.authUser) {
    return (
      <LoginPage
        loginStep={auth.loginStep}
        setLoginStep={auth.setLoginStep}
        loginEmail={auth.loginEmail}
        setLoginEmail={auth.setLoginEmail}
        loginOtp={auth.loginOtp}
        setLoginOtp={auth.setLoginOtp}
        loginLoading={auth.loginLoading}
        loginError={auth.loginError}
        setLoginError={auth.setLoginError}
        otpCountdown={auth.otpCountdown}
        handleRequestOtp={auth.handleRequestOtp}
        handleDemoLogin={auth.handleDemoLogin}
        handleVerifyOtp={auth.handleVerifyOtp}
        handleResendOtp={auth.handleResendOtp}
        apiReady={auth.apiReady}
      />
    );
  }

  return (
    <AuthContext.Provider
      value={{
        authToken: auth.authToken,
        authUser: auth.authUser,
        isAdmin: auth.isAdmin,
        authHeaders: auth.authHeaders,
        handleLogout: auth.handleLogout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
