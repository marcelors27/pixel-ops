const { app, BrowserWindow } = require("electron");
const { spawn } = require("node:child_process");
const http = require("node:http");
const path = require("node:path");

const port = Number(process.env.PIXEL_OPS_CONFIG_STUDIO_PORT || 5174);
const host = "127.0.0.1";
const url = `http://${host}:${port}`;
let serverProcess = null;
let mainWindow = null;

function appRoot() {
  return app.getAppPath();
}

function repoRoot() {
  return app.isPackaged ? path.join(process.resourcesPath, "pixel-ops") : path.resolve(__dirname, "../..");
}

function npmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function startConfigStudio() {
  serverProcess = spawn(npmCommand(), ["run", "dev", "--", "--host", host, "--port", String(port)], {
    cwd: appRoot(),
    env: {
      ...process.env,
      BROWSER: "none",
      PIXEL_OPS_REPO_ROOT: repoRoot(),
    },
    shell: process.platform === "win32",
    stdio: "inherit",
  });
}

function waitForServer(retries = 80) {
  return new Promise((resolve, reject) => {
    const poll = (remaining) => {
      const request = http.get(url, (response) => {
        response.resume();
        resolve();
      });
      request.on("error", () => {
        if (remaining <= 0) {
          reject(new Error(`Config Studio did not start at ${url}`));
          return;
        }
        setTimeout(() => poll(remaining - 1), 250);
      });
      request.setTimeout(800, () => {
        request.destroy();
      });
    };
    poll(retries);
  });
}

async function createWindow() {
  startConfigStudio();
  await waitForServer();
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 920,
    minWidth: 960,
    minHeight: 680,
    title: "Pixel OPs Config Studio",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  await mainWindow.loadURL(url);
}

app.whenReady().then(() => {
  createWindow().catch((error) => {
    console.error(error);
    app.quit();
  });
});

app.on("window-all-closed", () => {
  if (serverProcess) {
    serverProcess.kill();
    serverProcess = null;
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow().catch((error) => {
      console.error(error);
      app.quit();
    });
  }
});
