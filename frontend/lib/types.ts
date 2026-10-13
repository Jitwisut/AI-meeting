export type MeetingStatus =
  | "pending"
  | "processing"
  | "awaiting_review"
  | "reviewed"
  | "published"
  | "failed";

export type TopicStatus = "not_mentioned" | "mentioned" | "resolved" | "unclear";

export interface Evidence {
  segment_id: number;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface Topic {
  id: string;
  title: string;
  source: "agenda" | "discovered" | "manual";
  status: TopicStatus;
  resolution: string | null;
  evidence: Evidence[];
  verified_by: string | null;
}

export interface Decision {
  id: string;
  text: string;
  evidence: Evidence[];
}

export interface ActionItem {
  id: string;
  task: string;
  owner: string | null;
  due_date: string | null;
  status: "open" | "done";
  evidence: Evidence[];
}

export interface Summary {
  meeting_title: string;
  summary: string;
  topics: Topic[];
  decisions: Decision[];
  action_items: ActionItem[];
  open_questions: Decision[];
  validation_warnings?: string[];
  generated_by?: string;
  generated_at?: string;
}

export interface ReportMeta {
  version: number;
  is_approved: boolean;
  approved_version: number | null;
  approved_by: string | null;
  approved_at: string | null;
  exported_version: number | null;
  sharepoint_web_url: string | null;
  has_docx: boolean;
  updated_at: string | null;
  generated_by?: string;
}

export interface Job {
  stage: "download" | "convert" | "transcribe" | "summarize";
  status: "queued" | "running" | "succeeded" | "failed" | "skipped";
  error_code: string | null;
  error_message: string | null;
  retry_count: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface Publication {
  id: string;
  chat_id: string;
  chat_topic: string | null;
  message_id: string | null;
  status: "sending" | "sent" | "failed" | "unknown";
  report_version: number;
  reference_code: string;
  approved_by: string | null;
  sent_at: string | null;
  error_code: string | null;
  error_message: string | null;
  attempts: number;
  created_at: string | null;
}

export interface Meeting {
  id: string;
  title: string;
  status: MeetingStatus;
  source_type: "sharepoint" | "upload" | "recording";
  source_filename: string | null;
  source_web_url: string | null;
  language: string;
  created_at: string;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number | null;
  report: ReportMeta | null;
  agenda?: string[];
  audio_available?: boolean;
  processing_stale?: boolean;
  jobs?: Job[];
  publications?: Publication[];
}

export interface Segment {
  id: number;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface DriveEntry {
  id: string;
  name: string;
  is_folder: boolean;
  size: number | null;
  web_url: string | null;
  last_modified: string | null;
  drive_id: string | null;
}

export interface GroupChat {
  id: string;
  topic: string;
  member_count: number;
  last_updated: string | null;
}

export interface Me {
  user: { id: string; name: string; email: string | null };
  roles: string[];
  can_approve: boolean;
  capabilities: Record<string, { granted: boolean; scopes: string[]; reason?: string; mock?: boolean }>;
  preferences: { default_language?: string; default_site_id?: string; default_drive_id?: string };
  modes: { auth: string; graph: string; stt: string; summarizer: string };
}

export interface AppSettings {
  languages: { code: string; label: string }[];
  default_language: string;
  sharepoint: { allowed_site_ids: string[]; report_folder: string; report_drive_configured: boolean };
  policy: {
    max_upload_mb: number;
    max_audio_minutes: number;
    temp_audio_retention_hours: number;
    upload_formats: string[];
    recording_formats: string[];
    human_review_required: boolean;
    speaker_diarization: boolean;
  };
  providers: Record<string, string>;
}
