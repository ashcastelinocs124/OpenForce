"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { Proposal } from "@/lib/types";

export function EditModal({
  proposal,
  onClose,
  onSaved,
}: {
  proposal: Proposal;
  onClose: () => void;
  onSaved: () => void;
}) {
  const initial = proposal.diff_payload.after;
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, v == null ? "" : String(v)])),
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const parsed: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(draft)) {
        // attempt to keep numeric values numeric
        if (v !== "" && !isNaN(Number(v))) parsed[k] = Number(v);
        else parsed[k] = v;
      }
      await api.edit(proposal.id, parsed);
      onSaved();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-lg font-semibold">Edit proposed values</h3>
        <p className="mt-1 text-xs text-slate-500">
          Adjust before approving. Empty fields will be sent as empty string.
        </p>
        <div className="mt-4 space-y-3">
          {Object.entries(draft).map(([k, v]) => (
            <label key={k} className="block">
              <span className="block text-xs font-medium text-slate-600">{k}</span>
              <input
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                value={v}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              />
            </label>
          ))}
        </div>
        {err && <p className="mt-3 text-xs text-rose-700">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
