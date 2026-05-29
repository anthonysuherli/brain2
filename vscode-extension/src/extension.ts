/**
 * brain2 VS Code extension — main entry point.
 *
 * Activates on startup. Registers commands and wires interruption triggers
 * to the capture → API flow. The resume card is shown on demand via command.
 */

import * as vscode from "vscode";
import { Brain2Client } from "./api";
import { collectWorkspaceState, promptHypothesis } from "./capture";
import { showErrorCard, showLoadingCard, showResumeCard } from "./resume";
import { TriggerManager, type TriggerName } from "./triggers";

// Extension-level singletons
let client: Brain2Client | undefined;
let triggerManager: TriggerManager | undefined;
let cachedApiKey: string | undefined;
let statusBarItem: vscode.StatusBarItem | undefined;

// Debounce: don't fire two captures within 30 s of each other
let lastCaptureAt = 0;
const CAPTURE_DEBOUNCE_MS = 30_000;

// Auto-resume: set to true after a blur-triggered capture; cleared on focus-regain
let pendingResume = false;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = "$(brain) brain2";
  statusBarItem.tooltip = "brain2 context resume";
  statusBarItem.command = "brain2.resume";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  client = new Brain2Client(getApiUrl());

  // Commands
  context.subscriptions.push(
    vscode.commands.registerCommand("brain2.capture", () => runCapture("manual")),
    vscode.commands.registerCommand("brain2.resume", () => runResume()),
    vscode.commands.registerCommand("brain2.signIn", () => storeApiKey(context)),
    vscode.commands.registerCommand("brain2.explore", (project: string, kb: string) =>
      runExplore(project, kb)
    )
  );

  // Load cached API key
  cachedApiKey = await context.secrets.get("brain2.apiKey");
  if (!cachedApiKey) {
    // Fallback: plain settings (less secure but zero-friction for local dev)
    cachedApiKey = vscode.workspace.getConfiguration("brain2").get<string>("apiKey") ?? "";
  }

  // Start triggers
  triggerManager = new TriggerManager((trigger: TriggerName) => {
    if (trigger === "blur" || trigger === "git_checkout") {
      pendingResume = true;
    }
    runCapture(trigger);
  });
  triggerManager.start();
  context.subscriptions.push({ dispose: () => triggerManager?.dispose() });

  // Auto-resume on focus-regain if a capture happened during the blur
  context.subscriptions.push(
    vscode.window.onDidChangeWindowState((state) => {
      if (state.focused && pendingResume) {
        pendingResume = false;
        // Small delay so the window is fully focused before the card appears
        setTimeout(() => runResume(), 400);
      }
    })
  );
}

export function deactivate(): void {
  triggerManager?.dispose();
  statusBarItem?.dispose();
}

// ---------------------------------------------------------------------------
// Core flows
// ---------------------------------------------------------------------------

async function runCapture(trigger: TriggerName): Promise<void> {
  const now = Date.now();
  if (now - lastCaptureAt < CAPTURE_DEBOUNCE_MS && trigger !== "manual") {
    return;
  }
  lastCaptureAt = now;

  const key = await ensureApiKey();
  if (!key) return;

  const state = await collectWorkspaceState();
  const project = resolveProject(state.projectPath);
  const kb = state.branch ?? "main";

  // Hypothesis prompt — non-blocking; fires even if user doesn't answer
  let hypothesis: string | undefined;
  if (trigger !== "idle") {
    // Show prompt for blur/checkout/manual but not idle (avoids interruption)
    hypothesis = await promptHypothesis();
  }

  const payload = {
    project,
    kb,
    trigger,
    captured_at: new Date().toISOString(),
    branch: state.branch,
    git_diff_stat: state.gitDiffStat,
    open_files: state.openFiles,
    cursor_file: state.cursorFile,
    cursor_line: state.cursorLine,
    hypothesis,
    project_path: state.projectPath,
  };

  try {
    const c = getClient();
    await c.capture(payload, key);
    setStatus("$(check) context saved", 3000);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    vscode.window.showWarningMessage(`brain2: capture failed — ${msg}`);
  }
}

async function runResume(): Promise<void> {
  const key = await ensureApiKey();
  if (!key) return;

  const state = await collectWorkspaceState();
  const project = resolveProject(state.projectPath);
  const kb = state.branch ?? "main";

  showLoadingCard(project, kb);

  try {
    const c = getClient();
    const data = await c.resume(project, kb, key, state.cursorFile);
    showResumeCard(data, (msg) => {
      if (msg.command === "explore") {
        vscode.commands.executeCommand("brain2.explore", project, kb);
      }
    });
    const band = data.coverage;
    setStatus(`$(brain) ${band === "gap" ? "$(question) gap" : band === "rich" ? "$(check)" : "$(info)"} brain2`, 8000);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    showErrorCard(msg);
  }
}

async function runExplore(project: string, kb: string): Promise<void> {
  const key = await ensureApiKey();
  if (!key) return;

  // Ask what to explore — default to the current cursor context
  const state = await collectWorkspaceState();
  const defaultPrompt = state.cursorFile
    ? `Context around ${state.cursorFile}${state.branch ? ` on ${state.branch}` : ""}`
    : `${project} / ${kb}`;

  const prompt = await vscode.window.showInputBox({
    prompt: "What should brain2 explore?",
    value: defaultPrompt,
    ignoreFocusOut: true,
  });
  if (!prompt) return;

  setStatus("$(sync~spin) exploring…");

  try {
    const c = getClient();
    const { exploration_id } = await c.startExplore(project, kb, prompt, key);

    // Poll until completed / failed
    const POLL_PHASES: Record<string, string> = {
      planning: "$(sync~spin) planning…",
      searching: "$(sync~spin) searching…",
      crawling: "$(sync~spin) crawling…",
      extracting: "$(sync~spin) extracting…",
      merging: "$(sync~spin) merging…",
    };

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: `brain2: exploring "${prompt.slice(0, 60)}"`,
        cancellable: false,
      },
      async (progress) => {
        let lastStatus = "pending";
        while (true) {
          await sleep(2500);
          const s = await c.exploreStatus(exploration_id, key);

          if (s.status !== lastStatus) {
            lastStatus = s.status;
            const label = POLL_PHASES[s.status] ?? `$(sync~spin) ${s.status}…`;
            setStatus(label);
            progress.report({ message: s.status });
          }

          if (s.status === "completed") {
            setStatus(`$(check) ${s.finding_count} findings — refreshing card`, 5000);
            // Auto-refresh the resume card so the new findings appear
            await runResume();
            return;
          }
          if (s.status === "failed") {
            vscode.window.showErrorMessage(`brain2 explore failed: ${s.error ?? "unknown"}`);
            setStatus("$(brain) brain2");
            return;
          }
        }
      }
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage(`brain2 explore: ${msg}`);
    setStatus("$(brain) brain2");
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getClient(): Brain2Client {
  if (!client) {
    client = new Brain2Client(getApiUrl());
  }
  return client;
}

function getApiUrl(): string {
  return (
    vscode.workspace.getConfiguration("brain2").get<string>("apiUrl") ??
    "http://localhost:8002"
  );
}

function resolveProject(projectPath: string): string {
  const configured = vscode.workspace.getConfiguration("brain2").get<string>("project");
  if (configured) return configured;
  return projectPath.split("/").pop() ?? "workspace";
}

async function ensureApiKey(): Promise<string | undefined> {
  if (cachedApiKey) return cachedApiKey;
  vscode.window.showInformationMessage(
    "brain2: no API key set. Run the \"brain2: Sign In\" command.",
    "Sign In"
  ).then((action) => {
    if (action === "Sign In") {
      vscode.commands.executeCommand("brain2.signIn");
    }
  });
  return undefined;
}

async function storeApiKey(context: vscode.ExtensionContext): Promise<void> {
  const key = await vscode.window.showInputBox({
    prompt: "Paste your brain2 API key (from BRAIN2_API_KEY in your .env)",
    placeHolder: "brain2_live_...",
    password: true,
    ignoreFocusOut: true,
  });
  if (!key) return;
  cachedApiKey = key;
  await context.secrets.store("brain2.apiKey", key);
  vscode.window.showInformationMessage("brain2: API key saved.");
}

function setStatus(text: string, clearAfterMs?: number): void {
  if (!statusBarItem) return;
  statusBarItem.text = text;
  if (clearAfterMs) {
    setTimeout(() => {
      if (statusBarItem) statusBarItem.text = "$(brain) brain2";
    }, clearAfterMs);
  }
}
