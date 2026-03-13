"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Shield } from "lucide-react";

interface Props {
  loginStep: "email" | "otp";
  setLoginStep: (step: "email" | "otp") => void;
  loginEmail: string;
  setLoginEmail: (v: string) => void;
  loginOtp: string;
  setLoginOtp: (v: string) => void;
  loginLoading: boolean;
  loginError: string;
  setLoginError: (v: string) => void;
  otpCountdown: number;
  handleRequestOtp: (e: React.FormEvent) => void;
  handleDemoLogin: (role: string) => void;
  handleVerifyOtp: (e: React.FormEvent) => void;
  handleResendOtp: () => void;
  apiReady: boolean;
}

export function LoginPage({
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
  handleResendOtp,
  apiReady,
}: Props) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6 rounded-xl border border-border bg-card p-8 shadow-lg">
        <div className="flex flex-col items-center gap-2">
          <Shield className="h-10 w-10 text-primary" />
          <h1 className="text-xl font-bold tracking-tight">ClauseLens</h1>
          <p className="text-sm text-muted-foreground">
            Sign in with your government email
          </p>
        </div>

        {!apiReady && (
          <div className="flex items-center gap-2 rounded-md border border-yellow-700/40 bg-yellow-950/20 px-3 py-2 text-xs text-yellow-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            Waking up server, please wait…
          </div>
        )}

        {loginError && (
          <div className="rounded-md border border-red-700/40 bg-red-950/20 px-3 py-2 text-xs text-red-400">
            {loginError}
          </div>
        )}

        {loginStep === "email" ? (
          <form onSubmit={handleRequestOtp} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email address</Label>
              <Input
                id="email"
                type="email"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                placeholder="yourname@open.gov.sg"
                required
                autoFocus
              />
            </div>
            <Button type="submit" className="w-full" disabled={loginLoading || !apiReady}>
              {loginLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Send OTP
            </Button>
            <p className="text-center text-[10px] text-muted-foreground">
              Only @open.gov.sg and @tech.gov.sg emails are allowed.
            </p>
          </form>
        ) : (
          <form onSubmit={handleVerifyOtp} className="space-y-4">
            <p className="text-center text-sm text-muted-foreground">
              OTP sent to <span className="font-medium text-foreground">{loginEmail}</span>
            </p>
            <div className="space-y-2">
              <Label htmlFor="otp">Enter 6-digit OTP</Label>
              <Input
                id="otp"
                type="text"
                value={loginOtp}
                onChange={(e) =>
                  setLoginOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
                placeholder="000000"
                maxLength={6}
                required
                autoFocus
                className="text-center text-2xl tracking-[0.5em]"
              />
            </div>
            <div className="text-center text-xs text-muted-foreground">
              {otpCountdown > 0
                ? `Expires in ${Math.floor(otpCountdown / 60)}:${String(
                    otpCountdown % 60
                  ).padStart(2, "0")}`
                : "OTP expired"}
            </div>
            <Button
              type="submit"
              className="w-full"
              disabled={loginLoading || loginOtp.length !== 6 || otpCountdown === 0}
            >
              {loginLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Verify OTP
            </Button>
            <div className="flex justify-between text-xs">
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground underline"
                onClick={() => {
                  setLoginStep("email");
                  setLoginError("");
                }}
              >
                Change email
              </button>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground underline disabled:opacity-50"
                onClick={handleResendOtp}
                disabled={otpCountdown > 840}
              >
                Resend OTP
              </button>
            </div>
          </form>
        )}

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center text-[10px]">
            <span className="bg-card px-2 text-muted-foreground">Demo Accounts</span>
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 text-xs"
            onClick={() => handleDemoLogin("user")}
            disabled={loginLoading || !apiReady}
          >
            Demo User
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1 text-xs"
            onClick={() => handleDemoLogin("admin")}
            disabled={loginLoading || !apiReady}
          >
            Demo Admin
          </Button>
        </div>
      </div>
    </div>
  );
}
