/**
 * Workspace state collection — gathers everything observable from VS Code APIs
 * and a git subprocess call. Designed to be sub-second and never throw.
 */

import * as cp from "child_process";
import * as path from "path";
import * as vscode from "vscode";

export interface WorkspaceState {
  projectPath: string;
  openFiles: string[];
  cursorFile?: string;
  cursorLine?: number;
  branch?: string;
  gitDiffStat?: string;
}

export async function collectWorkspaceState(): Promise<WorkspaceState> {
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";

  const openFiles = vscode.workspace.textDocuments
    .filter((d) => !d.isUntitled && d.uri.scheme === "file")
    .map((d) => relative(d.uri.fsPath, workspaceRoot))
    .filter(Boolean);

  const editor = vscode.window.activeTextEditor;
  const cursorFile = editor ? relative(editor.document.uri.fsPath, workspaceRoot) : undefined;
  const cursorLine = editor ? editor.selection.active.line + 1 : undefined;

  const [branch, gitDiffStat] = await Promise.all([
    runGit(["rev-parse", "--abbrev-ref", "HEAD"], workspaceRoot),
    runGit(["diff", "--stat", "--no-color"], workspaceRoot),
  ]);

  return {
    projectPath: workspaceRoot,
    openFiles,
    cursorFile,
    cursorLine,
    branch: branch?.trim() || undefined,
    gitDiffStat: gitDiffStat?.trim() || undefined,
  };
}

export async function promptHypothesis(): Promise<string | undefined> {
  return vscode.window.showInputBox({
    prompt: "What were you working on? (press Enter to skip)",
    placeHolder: "e.g. Fixing the auth token refresh race condition",
    ignoreFocusOut: true,
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relative(filePath: string, root: string): string {
  if (!root || !filePath.startsWith(root)) {
    return path.basename(filePath);
  }
  return filePath.slice(root.length).replace(/^[/\\]/, "");
}

async function runGit(args: string[], cwd: string): Promise<string | undefined> {
  if (!cwd) return undefined;
  return new Promise((resolve) => {
    cp.exec(`git ${args.join(" ")}`, { cwd, timeout: 3000 }, (err, stdout) => {
      resolve(err ? undefined : stdout);
    });
  });
}
