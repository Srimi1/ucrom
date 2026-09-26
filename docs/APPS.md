# Apps and AI agents

ucrom is a normal arm64 Linux, so apps with a Linux ARM64 build run on it.

## App Hub

Open **App Hub** and tap **Install**. Everything installs from its official source into your home folder (no root needed) and gets a launcher on the home screen. Tap **Open** to start it.

| App | Source | Notes |
|---|---|---|
| Claude Code | npm `@anthropic-ai/claude-code` (ships a native linux-arm64 build) | needs Node 22, preinstalled in `/opt/node` |
| Codex CLI | npm `@openai/codex` (includes the linux-arm64 binary) | |
| Gemini CLI | npm `@google/gemini-cli` | |
| Antigravity | official download from antigravity.google | App Hub opens the download page; download the Linux ARM64 build in the browser, then tap Install again. Refuses non-ARM64 builds. |
| Visual Studio Code | Microsoft's apt repository (arm64 .deb, SHA-256 checked) | unpacked into your home, no apt changes |
| LLM | PyPI via pipx | |

Terminal agents (Claude Code, Codex, Gemini, LLM) open in the touch terminal in `~/Projects`. The on-screen keyboard has a terminal layout with Ctrl, Esc, Tab and arrows, so they're fully usable without a keyboard. When an agent exits, the shell stays open.

Desktop-sized apps (VS Code, Antigravity) get Phosh's scale-to-fit, so their windows fit the phone screen and respond to touch.

The catalog lives in `apps/catalog.yaml` and installers in `apps/installers/`. Add an app by adding both.

Proprietary apps are not baked into the image (licensing). Personal builds can preinstall them with `UCROM_PREINSTALL_AI=1`.

## Other ways to install

- `pipx install <tool>` for Python tools, `npm install -g <tool>` for Node tools (goes to `~/.npm-global`).
- Flatpak with the Flathub remote.
- `apt` for anything in Ubuntu 24.04 arm64.

## Limits

- x86-only apps don't run (no x86 emulator is included).
- The emulator test couldn't reach the Antigravity download site, so the test report installs VS Code (same VS Code/Electron base) in its place and says so.
