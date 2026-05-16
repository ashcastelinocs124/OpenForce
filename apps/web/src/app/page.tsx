"use client";

import useSWR from "swr";

import { ProposalCard } from "@/components/ProposalCard";
import { api } from "@/lib/api";

export default function Home() {
  const { data, error, isLoading, mutate } = useSWR("proposals/pending", () =>
    api.listProposals("pending"),
  );

  return (
    <main className="mx-auto max-w-3xl p-8">
      <header className="mb-6">
        <h1 className="text-3xl font-semibold">Pending proposals</h1>
        <p className="mt-1 text-sm text-slate-500">
          Review AI-proposed Salesforce updates. Approve, edit, or reject each one.
        </p>
      </header>

      {error && (
        <p className="rounded bg-rose-50 px-3 py-2 text-sm text-rose-700">
          Error loading proposals: {String(error)}
        </p>
      )}
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}

      <div className="space-y-4">
        {data?.length === 0 && (
          <p className="rounded border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            Inbox is clean — no pending proposals right now.
          </p>
        )}
        {data?.map((p) => (
          <ProposalCard key={p.id} proposal={p} onChange={() => mutate()} />
        ))}
      </div>
    </main>
  );
}
