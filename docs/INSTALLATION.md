# Installation Guide

Step-by-step instructions for installing Cartographer on macOS and Windows.

---

## Prerequisites

Both platforms require:

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.10 or later | 3.12 recommended |
| pip | bundled with Python | used to install Cartographer |
| Git | any recent version | required to clone the repository |
| Node.js | 18 or later | required to install Claude Code |
| Claude Code | latest | the CLI this tool extends |

---

## macOS

### 1. Install Python

The system Python that ships with macOS is too old. Install a current version via [Homebrew](https://brew.sh) (recommended) or the official installer.

**Via Homebrew (recommended):**

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.12
brew install python@3.12
```

Verify:

```bash
python3 --version
# Python 3.12.x
```

**Via the official installer:**

Download the macOS installer from [python.org/downloads](https://www.python.org/downloads/) and run it. The installer adds `python3` and `pip3` to your PATH automatically.

---

### 2. Install Node.js

Claude Code requires Node.js 18 or later.

**Via Homebrew:**

```bash
brew install node
```

**Via the official installer:**

Download from [nodejs.org](https://nodejs.org/) and run the macOS `.pkg` installer.

Verify:

```bash
node --version
# v20.x.x or later
```

---

### 3. Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

Verify:

```bash
claude --version
```

If the command is not found after install, add npm's global bin directory to your PATH:

```bash
echo 'export PATH="$(npm root -g)/../.bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

### 4. Install Cartographer

Cartographer is not yet published to PyPI. Install it directly from the GitHub repository.

**Option A — global install (simplest):**

```bash
pip3 install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli[embed]"
```

**Option B — inside a virtual environment (recommended for project isolation):**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli[embed]"
```

**Option C — editable install from a local clone (for contributors):**

```bash
git clone https://github.com/acn-hendrickacosta/cartographer.git
cd cartographer/cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[embed]"
```

The `[embed]` extra installs `fastembed`, which downloads a ~90 MB embedding model on first use. This only happens once and is cached in your home directory.

Verify:

```bash
cartographer --version
```

---

### 5. Initialize a project

Navigate to your project root and run:

```bash
cd my-project
cartographer init --stack python   # replace python with your stack
```

Supported stacks: `python`, `typescript`, `react`, `golang`, `rust`, `java`, `kotlin`, `angular`, `vue`, `swift`, `dart`.

After `init` completes, verify the setup:

```bash
cartographer doctor
```

All checks should pass. If any fail, the output explains what is missing and how to fix it.

---

### macOS troubleshooting

| Problem | Fix |
|---|---|
| `pip3: command not found` | Use `python3 -m pip install ...` instead |
| `cartographer: command not found` after install | Add `$(python3 -m site --user-base)/bin` to your `PATH` in `~/.zshrc` |
| `fastembed` model download hangs | Check your network connection; corporate proxies may block Hugging Face downloads |
| `lancedb` or `kuzu` fails to install | Ensure you are on Python 3.10+ and try `pip3 install --upgrade pip` before retrying |

---

## Windows

### 1. Install Python

Download the Python 3.12 Windows installer from [python.org/downloads](https://www.python.org/downloads/).

During installation:

- Check **"Add python.exe to PATH"** on the first screen — this is required.
- Leave all other defaults.

Verify in a new PowerShell window:

```powershell
python --version
# Python 3.12.x
```

**Alternative — install via winget:**

```powershell
winget install Python.Python.3.12
```

---

### 2. Enable long file path support (required)

Windows limits file paths to 260 characters by default. Cartographer's embedded databases and model cache use longer paths. You must enable long path support before proceeding.

Open PowerShell **as Administrator** and run:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

Then close and reopen PowerShell (no reboot required).

---

### 3. Install Node.js

Download the Windows installer (`.msi`) from [nodejs.org](https://nodejs.org/) and run it.

Verify in a new PowerShell window:

```powershell
node --version
# v20.x.x or later
```

---

### 4. Install Claude Code

```powershell
npm install -g @anthropic-ai/claude-code
```

Verify:

```powershell
claude --version
```

If `claude` is not recognized, close and reopen PowerShell — npm updates the PATH for new shells only.

---

### 5. Install Cartographer

Cartographer is not yet published to PyPI. Install it directly from the GitHub repository.

**Option A — global install (simplest):**

```powershell
pip install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli[embed]"
```

**Option B — inside a virtual environment (recommended):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli[embed]"
```

If PowerShell blocks script execution, run this once in an Administrator PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then re-run the activate command.

**Option C — editable install from a local clone (for contributors):**

```powershell
git clone https://github.com/acn-hendrickacosta/cartographer.git
cd cartographer\cli
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[embed]"
```

The `[embed]` extra installs `fastembed`, which downloads a ~90 MB embedding model on first use. This only happens once.

Verify:

```powershell
cartographer --version
```

---

### 6. Initialize a project

Open PowerShell in your project root:

```powershell
cd my-project
cartographer init --stack python   # replace python with your stack
```

After `init` completes, verify the setup:

```powershell
cartographer doctor
```

---

### Windows troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognized | Reinstall Python and check "Add python.exe to PATH", or add it manually in System Properties → Environment Variables |
| `cartographer` not recognized after install | Add `%APPDATA%\Python\Python312\Scripts` to your user PATH |
| `fastembed` install fails with a C++ error | Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) and retry |
| `lancedb` install fails | Ensure pip is up to date: `pip install --upgrade pip`, then retry |
| PowerShell activation blocked | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` in an Administrator PowerShell |
| Paths exceed limit | Enable long path support (Step 2 above) |

---

## Next steps

Once `cartographer doctor` passes:

| Task | Command |
|---|---|
| Add another language pack | `cartographer stack add typescript` |
| Index existing documentation | `cartographer seed docs/` |
| Bootstrap the knowledge base from code | Open a Claude Code session and run `/archaeology` |
| Open the local knowledge browser | `cartographer ui` |

For configuration options, see [CONFIGURATION.md](CONFIGURATION.md).  
For multi-developer (central topology) setup, see the [Multi-developer setup](../README.md#multi-developer-setup) section in the README.
