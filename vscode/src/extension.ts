/**
 * extension.ts
 *
 * Entry point for the VS Code extension. This extension starts the
 * django-lsp Python server and connects to it via LSP.
 *
 * Responsibilities:
 *   - Find Python interpreter
 *   - Start the LSP server as a subprocess
 *   - Connect the VS Code LSP client
 */

import * as vscode from "vscode";
import * as path from "path";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let outputChannel: vscode.OutputChannel;

export async function activate(context: vscode.ExtensionContext) {
  // Create output channel for logging
  outputChannel = vscode.window.createOutputChannel("Django Language Server");
  outputChannel.appendLine("Django Settings Autocomplete is now activating...");
  outputChannel.appendLine(`Extension path: ${context.extensionPath}`);
  outputChannel.show(true);

  console.log("Django Settings Autocomplete is now active.");

  // Find Python interpreter
  const pythonPath = await findPythonPath();
  outputChannel.appendLine(`Using Python path: ${pythonPath}`);
  console.log(`Django Language Server: Using Python path: ${pythonPath}`);

  if (!pythonPath) {
    vscode.window.showErrorMessage(
      "Django Language Server: Could not find Python interpreter. " +
      'Set "django-lsp.pythonPath" in your settings.'
    );
    return;
  }

  // Path to the bundled LSP server module (inside extension directory)
  const lspDir = path.join(context.extensionPath, "django_lsp");
  const vendorDir = path.join(context.extensionPath, "vendor");

  // For development: resolve path to top-level lsp/src
  // context.extensionPath is .../django-lsp/vscode
  // root is .../django-lsp
  // lspSrc is .../django-lsp/lsp/src
  const rootDir = path.resolve(context.extensionPath, "..");
  const lspSrcDir = path.join(rootDir, "lsp", "src");

  console.log(`Django Language Server: Server directory: ${lspDir}`);
  console.log(`Django Language Server: Vendor directory: ${vendorDir}`);
  console.log(`Django Language Server: JSP Source directory (Dev): ${lspSrcDir}`);

  // Set PYTHONPATH to include extension dir (for django_lsp) and vendor dir
  // AND the top-level source dir for development
  const pythonPath2 = [context.extensionPath, vendorDir, lspSrcDir].join(path.delimiter);
  const env = { ...process.env, PYTHONPATH: pythonPath2 };

  // Server options: run Python with -m django_lsp
  const serverOptions: ServerOptions = {
    run: {
      command: pythonPath,
      args: ["-m", "django_lsp"],
      options: {
        cwd: context.extensionPath,
        env: env,
      },
    },
    debug: {
      command: pythonPath,
      args: ["-m", "django_lsp"],
      options: {
        cwd: context.extensionPath,
        env: env,
      },
    },
  };

  // Client options
  const clientOptions: LanguageClientOptions = {
    // Only activate for Python settings files
    documentSelector: [
      {
        scheme: "file",
        language: "python",
        pattern: "**/settings.py",
      },
      {
        scheme: "file",
        language: "python",
        pattern: "**/settings/**/*.py",
      },
    ],
    synchronize: {
      // Watch settings.py files
      fileEvents: vscode.workspace.createFileSystemWatcher("**/settings*.py"),
      // Notify server when configuration changes
      configurationSection: "django-lsp",
    },
  };

  // Create and start the language client
  client = new LanguageClient(
    "django-lsp",
    "Django Language Server",
    serverOptions,
    clientOptions
  );

  // Start the client (also starts the server)
  await client.start();
  console.log("Django Language Server client started.");
}

export async function deactivate(): Promise<void> {
  if (client) {
    await client.stop();
  }
  console.log("Django Language Server has been deactivated.");
}

/**
 * Find the Python interpreter to use.
 */
async function findPythonPath(): Promise<string | undefined> {
  const fs = require("fs");
  const { execSync } = require("child_process");

  // Helper to check if a path exists and is executable
  const isValidPython = (p: string): boolean => {
    try {
      return fs.existsSync(p);
    } catch {
      return false;
    }
  };

  // 1. First priority: Check extension-specific setting
  const extConfig = vscode.workspace.getConfiguration("django-lsp");
  const configuredPath = extConfig.get<string>("pythonPath");
  if (configuredPath && configuredPath.trim() !== "" && isValidPython(configuredPath)) {
    console.log("Django Language Server: Using configured pythonPath");
    return configuredPath;
  }

  // 2. Try system python3/python first (most reliable)
  try {
    const systemPython = execSync("which python3 || which python", { encoding: "utf-8" }).trim();
    if (systemPython && isValidPython(systemPython)) {
      console.log("Django Language Server: Using system Python");
      return systemPython;
    }
  } catch {
    // which command failed
  }

  // 3. Try VS Code Python extension's interpreter
  const pythonExtension = vscode.extensions.getExtension("ms-python.python");
  if (pythonExtension) {
    try {
      if (!pythonExtension.isActive) {
        await pythonExtension.activate();
      }
      const pythonApi = pythonExtension.exports;
      if (pythonApi?.settings?.getExecutionDetails) {
        const details = pythonApi.settings.getExecutionDetails(
          vscode.workspace.workspaceFolders?.[0]?.uri
        );
        if (details?.execCommand?.[0] && isValidPython(details.execCommand[0])) {
          console.log("Django Language Server: Using Python extension path");
          return details.execCommand[0];
        }
      }
    } catch (e) {
      console.log("Django Language Server: Could not get Python from Python extension", e);
    }
  }

  // Last resort: just try "python3"
  return "python3";
}
