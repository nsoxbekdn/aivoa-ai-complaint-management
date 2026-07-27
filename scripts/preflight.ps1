# Pre-submission checks (Windows / PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File scripts\preflight.ps1
#
# Convenience only — nothing in the project depends on this script.
# It never prints the contents of any .env file.
#
# Deliberately flat: every command runs inline and its exit code is checked immediately.
# An earlier version wrapped the steps in a helper function and silently reported success
# without running them, which is worse than having no script at all.

$root = Split-Path -Parent $PSScriptRoot
$failures = @()

$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "No backend venv at $python. Create it with:"
    Write-Host "  cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# --- backend tests ------------------------------------------------------------
Write-Host ""
Write-Host "==> backend tests"
Set-Location (Join-Path $root 'backend')
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { $failures += 'backend tests' }

# --- alembic ------------------------------------------------------------------
Write-Host ""
Write-Host "==> alembic head"
& $python -m alembic heads
if ($LASTEXITCODE -ne 0) { $failures += 'alembic head' }

# --- frontend lint ------------------------------------------------------------
Write-Host ""
Write-Host "==> frontend lint"
Set-Location (Join-Path $root 'frontend')
& npm run lint
if ($LASTEXITCODE -ne 0) { $failures += 'frontend lint' }

# --- frontend build -----------------------------------------------------------
Write-Host ""
Write-Host "==> frontend build"
& npm run build
if ($LASTEXITCODE -ne 0) { $failures += 'frontend build' }

# --- tracked-secret scan ------------------------------------------------------
Write-Host ""
Write-Host "==> secret scan"
Set-Location $root
$patterns = 'gsk_[A-Za-z0-9]', 'sk-[A-Za-z0-9]{10,}', 'BEGIN (RSA|OPENSSH) PRIVATE KEY'
$hits = Get-ChildItem -Path $root -Recurse -File |
    Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules|dist|__pycache__|\.pytest_cache|\.git)\\' } |
    Where-Object { $_.Name -ne '.env' } |
    Select-String -Pattern $patterns -List |
    Select-Object -ExpandProperty Path

if ($hits) {
    # File names only — matched values are never printed.
    Write-Host "    Possible secrets in:"
    $hits | ForEach-Object { Write-Host "      $_" }
    $failures += 'secret scan'
} else {
    Write-Host "    No key-like strings found outside .env."
}

# --- summary ------------------------------------------------------------------
Write-Host ""
if ($failures.Count -eq 0) {
    Write-Host "All preflight checks passed."
    exit 0
}
Write-Host ("Failed: " + ($failures -join ', '))
exit 1
