import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getAdminEmergencyHalt, setAdminEmergencyHalt } from "../api/endpoints";

export function AdminSafetyPage() {
  const [adminKey, setAdminKey] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const haltQuery = useQuery({
    queryKey: ["admin-emergency-halt", adminKey],
    queryFn: () => getAdminEmergencyHalt(adminKey),
    enabled: adminKey.trim().length > 0
  });

  const setHaltMutation = useMutation({
    mutationFn: (payload: { halted: boolean; reason: string }) => setAdminEmergencyHalt(adminKey, payload.halted, payload.reason),
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
    if (!adminKey.trim()) {
      setError("Admin key is required");
      return;
    }
    if (!reason.trim()) {
      setError("Reason is required");
      return;
    }
    await setHaltMutation.mutateAsync({ halted, reason: reason.trim() });
  }

  return (
    <div className="grid">
      <section className="card">
        <h3>Admin Safety Controls</h3>
        <p className="muted">Use admin key to toggle global emergency trading halt.</p>
        <form className="grid">
          <label className="grid">
            Admin API Key
            <input type="password" value={adminKey} onChange={(e) => setAdminKey(e.target.value)} placeholder="X-Admin-Key" />
          </label>
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
        {!adminKey.trim() ? (
          <p className="muted">Enter admin key to fetch halt state.</p>
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
