/**
 * brain2 API client — thin wrapper over fetch for capture + resume.
 */

import * as vscode from "vscode";

export interface SnapshotPayload {
  project: string;
  kb: string;
  trigger: string;
  captured_at: string;
  branch?: string;
  git_diff_stat?: string;
  open_files: string[];
  cursor_file?: string;
  cursor_line?: number;
  terminal_tail?: string;
  hypothesis?: string;
  project_path: string;
}

export interface CaptureResponse {
  finding_id: string;
  coverage: string;
}

export interface ResumeResponse {
  coverage: string;
  preamble: string;
  card_html: string;
  project: string;
  kb: string;
  snapshot_count: number;
}

export class Brain2Client {
  private readonly apiUrl: string;

  constructor(apiUrl: string) {
    this.apiUrl = apiUrl.replace(/\/$/, "");
  }

  private get apiKey(): string {
    const secrets = vscode.workspace.getConfiguration("brain2");
    // API key is retrieved from SecretStorage via the extension — passed in here.
    // This method is called at call-time so it always reflects the current value.
    return (secrets.get<string>("_cachedApiKey") ?? "").trim();
  }

  private headers(apiKey: string): HeadersInit {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    };
  }

  async capture(payload: SnapshotPayload, apiKey: string): Promise<CaptureResponse> {
    const res = await fetch(`${this.apiUrl}/v1/capture`, {
      method: "POST",
      headers: this.headers(apiKey),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`brain2 capture failed: ${res.status} ${await res.text()}`);
    }
    return res.json() as Promise<CaptureResponse>;
  }

  async resume(project: string, kb: string, apiKey: string, query?: string): Promise<ResumeResponse> {
    const params = query ? `?query=${encodeURIComponent(query)}` : "";
    const res = await fetch(`${this.apiUrl}/v1/resume/${encodeURIComponent(project)}/${encodeURIComponent(kb)}${params}`, {
      headers: this.headers(apiKey),
    });
    if (!res.ok) {
      throw new Error(`brain2 resume failed: ${res.status} ${await res.text()}`);
    }
    return res.json() as Promise<ResumeResponse>;
  }

  async startExplore(
    project: string,
    kb: string,
    prompt: string,
    apiKey: string
  ): Promise<{ exploration_id: string; status: string }> {
    const res = await fetch(
      `${this.apiUrl}/v1/explore/${encodeURIComponent(project)}/${encodeURIComponent(kb)}`,
      {
        method: "POST",
        headers: this.headers(apiKey),
        body: JSON.stringify({ prompt }),
      }
    );
    if (!res.ok) {
      throw new Error(`brain2 explore failed: ${res.status} ${await res.text()}`);
    }
    return res.json() as Promise<{ exploration_id: string; status: string }>;
  }

  async exploreStatus(explorationId: string, apiKey: string): Promise<{
    exploration_id: string;
    status: string;
    finding_count: number;
    finding_ids: string[];
    completed_at: string | null;
    error: string | null;
  }> {
    const res = await fetch(`${this.apiUrl}/v1/explore/${explorationId}/status`, {
      headers: this.headers(apiKey),
    });
    if (!res.ok) {
      throw new Error(`brain2 status failed: ${res.status}`);
    }
    return res.json();
  }

  async health(): Promise<boolean> {
    try {
      const res = await fetch(`${this.apiUrl}/health`);
      return res.ok;
    } catch {
      return false;
    }
  }
}
