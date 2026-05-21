$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

$repoUrl = "https://github.com/dda428830-coco/liquidity-monitor.git"

Set-Location -LiteralPath $PSScriptRoot

function Invoke-Git {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$safeDirectory = ((Resolve-Path -LiteralPath $PSScriptRoot).Path -replace "\\", "/")
& git config --global --unset-all safe.directory "..." 2>$null
& git config --global --add safe.directory $safeDirectory

if (-not (Test-Path ".git")) {
    Invoke-Git init
}

Invoke-Git add .

$null = & git rev-parse --verify HEAD 2>$null
$hasCommit = ($LASTEXITCODE -eq 0)

$status = & git status --porcelain
if ($status) {
    Invoke-Git commit -m "Initial liquidity monitor"
} elseif (-not $hasCommit) {
    Invoke-Git commit --allow-empty -m "Initial liquidity monitor"
} else {
    Write-Host "No local changes to commit."
}

Invoke-Git branch -M main

$remote = & git remote
if ($remote -contains "origin") {
    Invoke-Git remote set-url origin $repoUrl
} else {
    Invoke-Git remote add origin $repoUrl
}

& git fetch origin main *> $null
if ($LASTEXITCODE -eq 0) {
    Invoke-Git pull --rebase origin main
}

Invoke-Git push -u origin main

Write-Host ""
Write-Host "Upload complete: https://github.com/dda428830-coco/liquidity-monitor"
