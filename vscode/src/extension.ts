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
import * as fs from "fs";
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

  // For development: resolve path to top-level python/src
  // context.extensionPath is .../django-lsp/vscode
  // root is .../django-lsp
  // pythonSrc is .../django-lsp/python/src
  const rootDir = path.resolve(context.extensionPath, "..");
  const lspSrcDir = path.join(rootDir, "python", "src");

  const devPackagePath = path.join(lspSrcDir, "django_lsp");
  const serverCwd = fs.existsSync(devPackagePath) ? lspSrcDir : context.extensionPath;

  console.log(`Django Language Server: Server directory: ${lspDir}`);
  console.log(`Django Language Server: Vendor directory: ${vendorDir}`);
  console.log(`Django Language Server: Python Source directory (Dev): ${lspSrcDir}`);
  console.log(`Django Language Server: Server cwd: ${serverCwd}`);

  // Set PYTHONPATH to include extension dir (for django_lsp), vendor dir,
  // top-level source dir for development, and workspace roots.
  const workspaceRoots = (
    vscode.workspace.workspaceFolders?.map((folder) => folder.uri.fsPath) || []
  ).filter(Boolean);
  const pythonPath2 = [
    lspSrcDir,
    context.extensionPath,
    vendorDir,
    ...workspaceRoots,
  ].join(path.delimiter);
  const env: NodeJS.ProcessEnv = { ...process.env, PYTHONPATH: pythonPath2 };

  const settingsInfo = findSettingsModule();
  if (settingsInfo) {
    env.DJANGO_SETTINGS_MODULE = settingsInfo.value;
    outputChannel.appendLine(
      `Using DJANGO_SETTINGS_MODULE (${settingsInfo.source}): ${settingsInfo.value}`
    );
  } else {
    outputChannel.appendLine("DJANGO_SETTINGS_MODULE not detected");
  }

  // Server options: run Python with -m django_lsp
  const serverOptions: ServerOptions = {
    run: {
      command: pythonPath,
      args: ["-m", "django_lsp"],
      options: {
        cwd: serverCwd,
        env: env,
      },
    },
    debug: {
      command: pythonPath,
      args: ["-m", "django_lsp"],
      options: {
        cwd: serverCwd,
        env: env,
      },
    },
  };

  // Client options
  const clientOptions: LanguageClientOptions = {
    // Activate for all Python files (settings and ORM usage)
    documentSelector: [
      {
        scheme: "file",
        language: "python",
      },
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

  // 2. Try VS Code Python extension's interpreter
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

  // 3. Try system python3/python
  try {
    const systemPython = execSync("which python3 || which python", { encoding: "utf-8" }).trim();
    if (systemPython && isValidPython(systemPython)) {
      console.log("Django Language Server: Using system Python");
      return systemPython;
    }
  } catch {
    // which command failed
  }

  // Last resort: just try "python3"
  return "python3";
}

type SettingsModuleInfo = {
  value: string;
  source: string;
};

function findSettingsModule(): SettingsModuleInfo | undefined {
  const extConfig = vscode.workspace.getConfiguration("django-lsp");
  const configured = extConfig.get<string>("djangoSettingsModule")?.trim();
  if (configured) {
    return { value: configured, source: "settings" };
  }

  const workspaceFolders = vscode.workspace.workspaceFolders ?? [];
  for (const folder of workspaceFolders) {
    const rootPath = folder.uri.fsPath;
    const managePyPath = findManagePyPath(rootPath);
    if (managePyPath) {
      const fromManagePy = parseSettingsModuleFromManagePy(managePyPath);
      if (fromManagePy) {
        return {
          value: fromManagePy,
          source: `manage.py (${managePyPath})`,
        };
      }
      const fromSettings = findSettingsModuleFromSettingsPy(
        path.dirname(managePyPath)
      );
      if (fromSettings) {
        return fromSettings;
      }
    }

    const fromSettings = findSettingsModuleFromSettingsPy(rootPath);
    if (fromSettings) {
      return fromSettings;
    }
  }

  return undefined;
}

function findManagePyPath(rootPath: string): string | undefined {
  const candidate = path.join(rootPath, "manage.py");
  if (fs.existsSync(candidate)) {
    return candidate;
  }

  try {
    const entries = fs.readdirSync(rootPath, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) {
        continue;
      }
      const nestedCandidate = path.join(rootPath, entry.name, "manage.py");
      if (fs.existsSync(nestedCandidate)) {
        return nestedCandidate;
      }
    }
  } catch (e) {
    console.log("Django Language Server: Failed to scan for manage.py", e);
  }

  return undefined;
}

function parseSettingsModuleFromManagePy(managePyPath: string): string | undefined {
  try {
    const contents = fs.readFileSync(managePyPath, "utf8");
    const match = contents.match(
      /DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([A-Za-z0-9_\.]+)['"]/,
    );
    return match?.[1];
  } catch (e) {
    console.log("Django Language Server: Failed to read manage.py", e);
    return undefined;
  }
}

function findSettingsModuleFromSettingsPy(
  rootPath: string
): SettingsModuleInfo | undefined {
  try {
    const entries = fs.readdirSync(rootPath, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) {
        continue;
      }
      const settingsPath = path.join(rootPath, entry.name, "settings.py");
      if (fs.existsSync(settingsPath)) {
        return {
          value: `${entry.name}.settings`,
          source: `settings.py (${settingsPath})`,
        };
      }
    }
  } catch (e) {
    console.log("Django Language Server: Failed to scan for settings.py", e);
  }

  return undefined;
}
