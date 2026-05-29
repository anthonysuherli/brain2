/**
 * Resume card webview panel — shows the 30-second "where I was" card.
 * Supports a postMessage callback so the card's "Explore?" button can
 * fire back to the extension.
 */

import * as vscode from "vscode";
import type { ResumeResponse } from "./api";

type MessageHandler = (msg: { command: string; [k: string]: unknown }) => void;

let panel: vscode.WebviewPanel | undefined;
let currentHandler: MessageHandler | undefined;

export function showResumeCard(data: ResumeResponse, onMessage?: MessageHandler): void {
  const column = vscode.ViewColumn.Beside;
  currentHandler = onMessage;

  if (panel) {
    panel.reveal(column);
    panel.webview.html = data.card_html;
    panel.title = `Resume — ${data.project}/${data.kb}`;
    return;
  }

  panel = vscode.window.createWebviewPanel(
    "brain2.resumeCard",
    `Resume — ${data.project}/${data.kb}`,
    { viewColumn: column, preserveFocus: true },
    {
      enableScripts: true,
      localResourceRoots: [],
    }
  );

  panel.webview.html = data.card_html;

  panel.webview.onDidReceiveMessage((msg) => {
    currentHandler?.(msg);
  });

  panel.onDidDispose(() => {
    panel = undefined;
    currentHandler = undefined;
  });
}

export function showLoadingCard(project: string, kb: string): void {
  const html = `<!DOCTYPE html><html><body style="padding:20px;font-family:system-ui;color:#6E6E73">
    <p style="font-size:13px">Loading context for <strong>${escHtml(project)} / ${escHtml(kb)}</strong>…</p>
  </body></html>`;
  showResumeCard({ card_html: html, coverage: "gap", preamble: "", project, kb });
}

export function showErrorCard(msg: string): void {
  if (!panel) return;
  panel.webview.html = `<!DOCTYPE html><html><body style="padding:20px;font-family:system-ui;color:#9C2C1F">
    <p><strong>brain2 error:</strong> ${escHtml(msg)}</p>
  </body></html>`;
}

function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
