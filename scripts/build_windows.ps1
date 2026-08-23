$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The project virtual environment was not found at $Python"
}

Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean "localization-workflow.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    $Release = Join-Path $ProjectRoot "dist\Localization Workflow"
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ".env.example") -Destination $Release
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "LICENSE") -Destination $Release
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs\third-party.md") -Destination $Release
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs\user-guide.md") -Destination $Release
    $Archive = Join-Path $ProjectRoot "dist\Localization-Workflow-1.0.0rc1-windows-x64.zip"
    Compress-Archive -LiteralPath $Release -DestinationPath $Archive -CompressionLevel Optimal -Force
}
finally {
    Pop-Location
}

Write-Host "Windows package and versioned archive created under dist"
