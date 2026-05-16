export type ProposalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "failed"
  | "failed_validation";

export type SfObjectType = "Account" | "Contact" | "Opportunity" | "Task";

export interface Proposal {
  id: string;
  email_id: string;
  sf_object_type: SfObjectType;
  sf_record_id: string | null;
  diff_payload: {
    before: Record<string, unknown>;
    after: Record<string, unknown>;
  };
  reasoning: string;
  confidence: number;
  status: ProposalStatus;
  error: string | null;
}
