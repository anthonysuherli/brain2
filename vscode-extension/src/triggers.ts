/**
 * Interruption triggers — detect blur, git checkout, and idle.
 *
 * Each trigger fires a callback with the trigger name. The extension
 * wires these callbacks to the capture flow.
 */

import * as vscode from "vscode";

export type TriggerName = "blur" | "git_checkout" | "idle" | "manual";
export type TriggerCallback = (trigger: TriggerName) => void;

export class TriggerManager {
  private disposables: vscode.Disposable[] = [];
  private idleTimer: ReturnType<typeof setTimeout> | undefined;
  private lastActivityAt = Date.now();
  private readonly callback: TriggerCallback;

  constructor(callback: TriggerCallback) {
    this.callback = callback;
  }

  start(): void {
    const cfg = vscode.workspace.getConfiguration("brain2");

    if (cfg.get<boolean>("enableBlurTrigger", true)) {
      this.disposables.push(
        vscode.window.onDidChangeWindowState((state) => {
          if (!state.focused) {
            this.fire("blur");
          }
        })
      );
    }

    if (cfg.get<boolean>("enableGitCheckoutTrigger", true)) {
      const gitHeadPattern = new vscode.RelativePattern(
        vscode.workspace.workspaceFolders?.[0] ?? "",
        ".git/HEAD"
      );
      const watcher = vscode.workspace.createFileSystemWatcher(gitHeadPattern);
      this.disposables.push(
        watcher,
        watcher.onDidChange(() => this.fire("git_checkout"))
      );
    }

    if (cfg.get<boolean>("enableIdleTrigger", true)) {
      const threshold = cfg.get<number>("idleThresholdSeconds", 300) * 1000;
      // Reset timer on any editor activity
      this.disposables.push(
        vscode.workspace.onDidChangeTextDocument(() => this.resetIdle(threshold)),
        vscode.window.onDidChangeActiveTextEditor(() => this.resetIdle(threshold)),
        vscode.window.onDidChangeTextEditorSelection(() => this.resetIdle(threshold))
      );
      this.resetIdle(threshold);
    }
  }

  dispose(): void {
    this.disposables.forEach((d) => d.dispose());
    this.disposables = [];
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
    }
  }

  private fire(trigger: TriggerName): void {
    this.callback(trigger);
  }

  private resetIdle(threshold: number): void {
    this.lastActivityAt = Date.now();
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
    }
    this.idleTimer = setTimeout(() => {
      if (Date.now() - this.lastActivityAt >= threshold) {
        this.fire("idle");
      }
    }, threshold);
  }
}
