# Troubleshooting

Common issues and solutions when using M4.

---

## Installation issues

### `m4` command opens GNU M4 instead of the CLI

On macOS and Linux, `m4` is a built-in system utility (a macro processor). If you get unexpected output when running `m4`, your virtual environment isn't activated.

**Fix:** Activate your virtual environment first:

=== "macOS / Linux"

    ```bash
    cd my-research
    source .venv/bin/activate
    m4 status  # Should now work
    ```

=== "Windows"

    ```powershell
    cd my-research
    .venv\Scripts\activate
    m4 status  # Should now work
    ```

Alternatively, use `uv run m4 [command]` to run within the project environment without activating it.

### `uv: command not found`

The `uv` installer didn't add itself to your PATH, or you haven't restarted your terminal.

**Fix:**

1. Close and reopen your terminal
2. If still not found, run the install command again:

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

### Permission errors during installation

=== "macOS / Linux"

    Do **not** use `sudo` with `uv` or `pip`. If you get permission errors, make sure you're using a virtual environment:

    ```bash
    cd my-research
    source .venv/bin/activate
    ```

=== "Windows"

    If you see "execution of scripts is disabled on this system":

    ```powershell
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
    ```

---

## Dataset issues

### "Parquet not found" error

The dataset hasn't been initialized or the database is corrupted.

**Fix:**

```bash
m4 init mimic-iv-demo --force
```

The `--force` flag recreates the database from scratch.

### Download stalls or fails partway through

The `wget` download was interrupted. The download commands use flags (`-N -c`) that make them safe to resume.

**Fix:** Re-run the exact same `wget` command. It will pick up where it left off.

### Not enough disk space

Check how much space you need before downloading:

| Dataset | Total disk space needed |
|---------|----------------------|
| mimic-iv-demo | ~50 MB |
| mimic-iv | ~26 GB |
| mimic-iv-note | ~13 GB |
| eicu | ~21 GB |

Free up space or use [BigQuery](guides/bigquery.md) for cloud-based access without downloading files.

### `wget` is not installed

=== "macOS"

    ```bash
    brew install wget
    ```

    If you don't have Homebrew: visit [brew.sh](https://brew.sh/)

=== "Windows"

    ```powershell
    winget install GnuWin32.Wget
    ```

=== "Linux (Debian/Ubuntu)"

    ```bash
    sudo apt install wget
    ```

---

## MCP connection issues

### AI client won't connect to M4

1. **Check your configuration** — make sure the JSON in your MCP settings is valid (no trailing commas, correct paths)
2. **Restart the client** — changes to MCP configuration require a full restart
3. **Check client logs:**
    - Claude Desktop: Help → View Logs
    - Cursor: check the MCP panel in settings
4. **Regenerate config:**

    ```bash
    m4 config claude --quick   # For Claude Desktop
    m4 config --quick          # For other clients
    ```

### Tools not appearing in the AI client

1. Make sure a dataset is initialized: `m4 status`
2. Make sure the AI client was restarted after config changes
3. Check that the MCP server can start: `uv run m4-infra` (should print nothing and wait for input)

---

## Windows-specific issues

### Execution policy prevents activation

If `.venv\Scripts\activate` fails with a policy error:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Path too long errors

Enable long paths in Windows:

1. Open **Group Policy Editor** (gpedit.msc)
2. Navigate to Computer Configuration → Administrative Templates → System → Filesystem
3. Enable "Enable Win32 long paths"

Or set via registry:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

### Virtual environment activation syntax

On Windows, use backslashes:

```powershell
.venv\Scripts\activate    # PowerShell
.venv\Scripts\activate.bat  # Command Prompt (cmd)
```

---

## BigQuery issues

### "Access Denied" error

- Ensure you've completed PhysioNet credentialing for the dataset
- Verify your Google account is linked to your PhysioNet account
- Re-authenticate: `gcloud auth application-default login`

### "Project not found" error

- Double-check the project ID (it's your billing project, not `physionet-data`)
- Ensure BigQuery API is enabled in your GCP project

See the [BigQuery Guide](guides/bigquery.md) for full setup instructions.

---

## Getting help

If your issue isn't listed here:

1. Check the [GitHub Issues](https://github.com/hannesill/m4/issues) for similar problems
2. Open a new issue with:
    - Your operating system
    - The command you ran
    - The full error message
    - Output of `m4 status`
