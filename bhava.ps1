param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Require-Uv {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is not installed. Run '.\bhava.ps1 bootstrap' and follow the documented official installation step."
    }
}

function Ensure-LocalConfig {
    $local = Join-Path $RepoRoot "config\local.toml"
    $example = Join-Path $RepoRoot "config\local.example.toml"
    if (-not (Test-Path $local) -and (Test-Path $example)) {
        Copy-Item $example $local
        Write-Host "Created config\local.toml from example (not overwriting if present later)."
    }
}

switch ($Command.ToLowerInvariant()) {
    "bootstrap" {
        Write-Host "Bhāva Library bootstrap"
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "Git is required. Install Git for Windows from https://git-scm.com/download/win"
        }
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Write-Host "uv is not installed."
            Write-Host "Install from the official installer: https://docs.astral.sh/uv/getting-started/installation/"
            Write-Host "After installing uv, re-run: .\bhava.ps1 bootstrap"
            exit 25
        }
        Ensure-LocalConfig
        & uv python install 3.14
        & uv sync --all-extras
        $dirs = @(
            "data\catalog",
            "data\originals\iskcon-education\documents",
            "data\originals\iskcon-education\office",
            "data\originals\iskcon-education\images",
            "data\originals\iskcon-education\archives",
            "data\originals\iskcon-education\audio",
            "data\originals\iskcon-education\video",
            "data\originals\iskcon-education\unknown",
            "data\staging",
            "data\quarantine",
            "data\snapshots",
            "data\cache",
            "data\derived",
            "data\backups",
            "logs",
            "reports\generated"
        )
        foreach ($d in $dirs) {
            New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot $d) | Out-Null
        }
        & uv run bhava-lib doctor
        & uv run pytest -q tests/unit tests/safety
        exit $LASTEXITCODE
    }
    "help" {
        Write-Host "Commands: bootstrap doctor scan resolve estimate acquire resume status verify index report backup restore-check serve copyright"
        Write-Host "Curation: curate snapshot|enrich|classify|build-views|review-report|integrity|sunday-school|candidates"
        Write-Host "Archive: archive-pack archive-restore-check"
    }
    default {
        Require-Uv
        & uv run bhava-lib $Command @Arguments
        exit $LASTEXITCODE
    }
}
