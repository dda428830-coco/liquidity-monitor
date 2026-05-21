$ErrorActionPreference = "Stop"

$repoUrl = "https://github.com/dda428830-coco/liquidity-monitor.git"

Set-Location -LiteralPath $PSScriptRoot

$safeDirectory = ((Resolve-Path -LiteralPath $PSScriptRoot).Path -replace "\\", "/")
git config --global --unset-all safe.directory "..." 2>$null
git config --global --add safe.directory $safeDirectory

if (-not (Test-Path ".git")) {
    git init
}

git add .

$null = git rev-parse --verify HEAD 2>$null
$hasCommit = ($LASTEXITCODE -eq 0)

$status = git status --porcelain
if ($status) {
    git commit -m "Initial liquidity monitor"
} elseif (-not $hasCommit) {
    git commit --allow-empty -m "Initial liquidity monitor"
} else {
    Write-Host "No local changes to commit."
}

git branch -M main

$remote = git remote
if ($remote -contains "origin") {
    git remote set-url origin $repoUrl
} else {
    git remote add origin $repoUrl
}

git fetch origin main 2>$null
if ($LASTEXITCODE -eq 0) {
    git pull --rebase origin main
}

git push -u origin main

Write-Host ""
Write-Host "Upload complete: https://github.com/dda428830-coco/liquidity-monitor"
