"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { Proposal } from "@/lib/types";

import { ConfidenceBadge } from "./ConfidenceBadge";
import { DiffView } from "./DiffView";
import { EditModal } from "./EditModal";

export function ProposalCard({
  proposal,
  onChange,
}: {
  proposal: Proposal;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  const action = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    try {
      await fn();
      onChange();
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="rounded-lg border bg-white p-4 shadow-sm">
      <header className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-medium">
            {proposal.sf_record_id ? "Update " : "Create "}
            {proposal.sf_object_type}
          </h2>
          <p className="text-xs text-slate-500">
            {proposal.sf_record_id ?? "(new record)"}
          </p>
        </div>
        <ConfidenceBadge value={proposal.confidence} />
      </header>

      <div className="mt-3">
        <DiffView
          before={proposal.diff_payload.before}
          after={proposal.diff_payload.after}
        />
      </div>

      <p className="mt-3 text-sm text-slate-700">
        <strong>Reasoning:</strong> {proposal.reasoning}
      </p>

      {proposal.error && (
        <p className="mt-2 rounded bg-rose-50 px-2 py-1 text-xs text-rose-800">
          {proposal.error}
        </p>
      )}

      <footer className="mt-4 flex gap-2">
        <button
          disabled={busy}
          onClick={action(() => api.approve(proposal.id))}
          className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          disabled={busy}
          onClick={() => setEditing(true)}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50"
        >
          Edit
        </button>
        <button
          disabled={busy}
          onClick={action(() => api.reject(proposal.id))}
          className="rounded bg-white px-3 py-1.5 text-sm font-medium text-rose-700 ring-1 ring-rose-200 hover:bg-rose-50 disabled:opacity-50"
        >
          Reject
        </button>
      </footer>

      {editing && (
        <EditModal
          proposal={proposal}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            onChange();
          }}
        />
      )}
    </article>
  );
}
