import type { Proposal, ProposalStatus } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  listProposals: (status: ProposalStatus = "pending") =>
    req<Proposal[]>(`/proposals?status=${status}`),
  getProposal: (id: string) => req<Proposal>(`/proposals/${id}`),
  approve: (id: string) => req<Proposal>(`/proposals/${id}/approve`, { method: "POST" }),
  reject: (id: string) => req<Proposal>(`/proposals/${id}/reject`, { method: "POST" }),
  edit: (id: string, after: Record<string, unknown>) =>
    req<Proposal>(`/proposals/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ after }),
    }),
};
