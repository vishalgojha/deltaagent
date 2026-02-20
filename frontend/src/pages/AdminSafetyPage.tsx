import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { adminSessionLogin, getAdminEmergencyHalt, setAdminEmergencyHalt } from "../api/endpoints";
import { clearAdminSessionToken, getAdminSessionToken, saveAdminSessionToken } from "../store/adminSession";

function EyeIcon({ visible }: { visible: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
      {visible ? (
        <path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A10 10 0 0 1 12 5c4.9 0 8.7 3.1 10 7-0.6 1.7-1.7 3.2-3.3 4.4M6.1 6.1C4.5 7.3 3.3 8.9 2.6 11c1.3 3.9 5.1 7 10 7 1 0 1.9-0.1 2.8-0.4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      ) : (
        <path d="M2 12c1.3-3.9 5.1-7 10-7s8.7 3.1 10 7c-1.3 3.9-5.1 7-10 7S3.3 15.9 2 12zm10-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      )}
    </svg>
  );
}

export function AdminSafetyPage() {
  const [adminKeyInput, setAdminKeyInput] = useState("");
  const [showAdminKey, setShowAdminKey] = useState(false);
  const [adminToken, setAdminToken] = useState(() => getAdminSessionToken());
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const haltQuery = useQuery({
    queryKey: ["admin-emergency-halt", adminToken],
    queryFn: () => getAdminEmergencyHalt(adminToken),
    enabled: adminToken.trim().length > 0
  });

  const adminLoginMutation = useMutation({
    mutationFn: (adminKey: string) => adminSessionLogin(adminKey),
    onSuccess: (data) => {
      saveAdminSessionToken(data.access_token);
      setAdminToken(data.access_token);
      setAdminKeyInput("");
      setSuccess("Admin session unlocked.");
      setError("");
      haltQuery.refetch();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to unlock admin session");
      setSuccess("");
    }
  });

  const setHaltMutation = useMutation({
    mutationFn: (payload: { halted: boolean; reason: string }) => setAdminEmergencyHalt(adminToken, payload.halted, payload.reason),
    onSuccess: (data) => {
      setSuccess(`Updated: halted=${String(data.halted)} by ${data.updated_by}`);
      setError("");
      haltQuery.refetch();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to update emergency halt");
      setSuccess("");
    }
  });

  async function onSubmit(event: FormEvent, halted: boolean) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (!adminToken.trim()) {
      setError("Admin session is required");
      return;
    }
    if (!reason.trim()) {
      setError("Reason is required");
      return;
    }
    await setHaltMutation.mutateAsync({ halted, reason: reason.trim() });
  }

  function onClearSession() {
    clearAdminSessionToken();
    setAdminToken("");
    setAdminKeyInput("");
    setSuccess("Admin session cleared.");
    setError("");
  }

  return (
    <div className="grid admin-safety-page">
      <section className="card">
        <h3>Admin Safety Controls</h3>
        <p className="muted">Unlock admin session, then toggle global emergency trading halt.</p>
        <form className="grid">
          <label className="grid">
            Admin API Key
            <div className="password-field">
              <input
                type={showAdminKey ? "text" : "password"}
                value={adminKeyInput}
                onChange={(e) => setAdminKeyInput(e.target.value)}
                placeholder="Enter once to unlock"
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowAdminKey((prev) => !prev)}
                aria-label={showAdminKey ? "Hide admin API key" : "Show admin API key"}
                title={showAdminKey ? "Hide admin API key" : "Show admin API key"}
              >
                <EyeIcon visible={showAdminKey} />
              </button>
            </div>
          </label>
          <div className="row">
            <button type="button" className="secondary" onClick={() => void adminLoginMutation.mutateAsync(adminKeyInput.trim())}>
              {adminLoginMutation.isPending ? "Unlocking..." : "Unlock Admin"}
            </button>
            <button type="button" className="secondary" onClick={onClearSession} disabled={!adminToken}>
              Lock Admin
            </button>
          </div>
          <label className="grid">
            Reason
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why halt/resume?" />
          </label>
          <div className="row">
            <button onClick={(e) => void onSubmit(e, true)} disabled={setHaltMutation.isPending}>
              Halt Trading
            </button>
            <button className="secondary" onClick={(e) => void onSubmit(e, false)} disabled={setHaltMutation.isPending}>
              Resume Trading
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h3>Current Global Halt State</h3>
        {!adminToken.trim() ? (
          <p className="muted">Unlock admin session to fetch halt state.</p>
        ) : haltQuery.isLoading ? (
          <p className="muted">Loading...</p>
        ) : haltQuery.data ? (
          <div className="grid">
            <p>Halted: {String(haltQuery.data.halted)}</p>
            <p>Reason: {haltQuery.data.reason || "-"}</p>
            <p>Updated By: {haltQuery.data.updated_by}</p>
            <p>Updated At: {haltQuery.data.updated_at}</p>
          </div>
        ) : (
          <p className="muted">No data</p>
        )}
      </section>

      {error && <p style={{ color: "#991b1b" }}>{error}</p>}
      {success && <p style={{ color: "#166534" }}>{success}</p>}
    </div>
  );
}
