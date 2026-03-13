"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AuthUser {
  userId: number;
  email: string;
  name: string;
  role: string;
}

export default function useAuth() {
  const [authToken, setAuthToken] = useState<string | null>(() =>
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null
  );
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      return JSON.parse(localStorage.getItem("auth_user") || "null");
    } catch {
      return null;
    }
  });
  const [loginStep, setLoginStep] = useState<"email" | "otp">("email");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginOtp, setLoginOtp] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [otpCountdown, setOtpCountdown] = useState(0);
  const [checkingAuth, setCheckingAuth] = useState(true);

  const isAdmin = authUser?.role === "admin";

  const authHeaders = useCallback(
    (): Record<string, string> =>
      authToken ? { Authorization: `Bearer ${authToken}` } : {},
    [authToken]
  );

  // Validate token on mount
  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.success) {
            setAuthUser(data.data);
            setAuthToken(token);
            localStorage.setItem("auth_user", JSON.stringify(data.data));
          } else {
            localStorage.removeItem("auth_token");
            localStorage.removeItem("auth_user");
            setAuthToken(null);
            setAuthUser(null);
          }
        })
        .catch(() => {
          localStorage.removeItem("auth_token");
          localStorage.removeItem("auth_user");
          setAuthToken(null);
          setAuthUser(null);
        })
        .finally(() => setCheckingAuth(false));
    } else {
      setCheckingAuth(false);
    }
  }, []);

  // OTP countdown timer
  useEffect(() => {
    if (otpCountdown <= 0) return;
    const timer = setInterval(() => {
      setOtpCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [otpCountdown]);

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    setLoginLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/request-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail }),
      });
      const data = await res.json();
      if (data.success) {
        setLoginStep("otp");
        setOtpCountdown(900);
      } else {
        setLoginError(data.error || "Failed to send OTP");
      }
    } catch {
      setLoginError("Network error. Please try again.");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    setLoginLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: loginEmail, otp: loginOtp }),
      });
      const data = await res.json();
      if (data.success) {
        const { token, user } = data.data;
        localStorage.setItem("auth_token", token);
        localStorage.setItem("auth_user", JSON.stringify(user));
        setAuthToken(token);
        setAuthUser(user);
        setLoginStep("email");
        setLoginEmail("");
        setLoginOtp("");
      } else {
        setLoginError(data.error || "Invalid OTP");
      }
    } catch {
      setLoginError("Network error. Please try again.");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleDemoLogin = async (role: string) => {
    setLoginError("");
    setLoginLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/demo-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ role }),
      });
      const data = await res.json();
      if (data.success) {
        const { token, user } = data.data;
        localStorage.setItem("auth_token", token);
        localStorage.setItem("auth_user", JSON.stringify(user));
        setAuthToken(token);
        setAuthUser(user);
      } else {
        setLoginError(data.error || "Demo login failed");
      }
    } catch {
      setLoginError("Network error. Please try again.");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {}
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    setAuthToken(null);
    setAuthUser(null);
    setLoginStep("email");
  };

  const handleResendOtp = async () => {
    if (otpCountdown > 840) return;
    setLoginError("");
    setLoginLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/request-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail }),
      });
      const data = await res.json();
      if (data.success) {
        setOtpCountdown(900);
        setLoginOtp("");
      } else {
        setLoginError(data.error || "Failed to resend OTP");
      }
    } catch {
      setLoginError("Network error.");
    } finally {
      setLoginLoading(false);
    }
  };

  return {
    authToken,
    authUser,
    isAdmin,
    checkingAuth,
    authHeaders,
    loginStep,
    setLoginStep,
    loginEmail,
    setLoginEmail,
    loginOtp,
    setLoginOtp,
    loginLoading,
    loginError,
    setLoginError,
    otpCountdown,
    handleRequestOtp,
    handleDemoLogin,
    handleVerifyOtp,
    handleLogout,
    handleResendOtp,
  };
}
