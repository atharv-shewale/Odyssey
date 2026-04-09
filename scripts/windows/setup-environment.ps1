# Odyssey Environment Setup Script for Windows
# Run as Administrator

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  Odyssey Trading Bot Setup" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ Please run PowerShell as Administrator!" -ForegroundColor Red
    exit 1
}

# 1. Install Chocolatey
Write-Host "📦 Installing Chocolatey..." -ForegroundColor Yellow
if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
    Write-Host "✅ Chocolatey installed" -ForegroundColor Green
} else {
    Write-Host "✅ Chocolatey already installed" -ForegroundColor Green
}

# Refresh environment
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 2. Install Git
Write-Host "`n📦 Installing Git..." -ForegroundColor Yellow
choco install git -y
Write-Host "✅ Git installed" -ForegroundColor Green

# 3. Install Node.js
Write-Host "`n📦 Installing Node.js..." -ForegroundColor Yellow
choco install nodejs-lts -y
Write-Host "✅ Node.js installed" -ForegroundColor Green

# 4. Install Python
Write-Host "`n📦 Installing Python 3.11..." -ForegroundColor Yellow
choco install python311 -y
Write-Host "✅ Python installed" -ForegroundColor Green

# 5. Install Docker Desktop
Write-Host "`n📦 Installing Docker Desktop..." -ForegroundColor Yellow
choco install docker-desktop -y
Write-Host "✅ Docker Desktop installed" -ForegroundColor Green
Write-Host "⚠️  Please restart your computer after Docker Desktop installation" -ForegroundColor Yellow

# 6. Install VS Code (Optional)
Write-Host "`n📦 Installing VS Code..." -ForegroundColor Yellow
choco install vscode -y
Write-Host "✅ VS Code installed" -ForegroundColor Green

# Refresh environment again
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 7. Verify installations
Write-Host "`n🔍 Verifying installations..." -ForegroundColor Yellow
Write-Host ""

# Git
try {
    $gitVersion = git --version
    Write-Host "✅ Git: $gitVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Git not found" -ForegroundColor Red
}

# Node.js
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found" -ForegroundColor Red
}

# npm
try {
    $npmVersion = npm --version
    Write-Host "✅ npm: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ npm not found" -ForegroundColor Red
}

# Python
try {
    $pythonVersion = python --version
    Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found" -ForegroundColor Red
}

# pip
try {
    $pipVersion = pip --version
    Write-Host "✅ pip: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ pip not found" -ForegroundColor Red
}

# Docker
try {
    $dockerVersion = docker --version
    Write-Host "✅ Docker: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Docker not found - may need restart" -ForegroundColor Yellow
}

# 8. Install global npm packages
Write-Host "`n📦 Installing global npm packages..." -ForegroundColor Yellow
npm install -g @grpc/proto-loader grpc-tools pm2
Write-Host "✅ Global npm packages installed" -ForegroundColor Green

# 9. Upgrade pip and install global Python packages
Write-Host "`n📦 Installing global Python packages..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install virtualenv
Write-Host "✅ Global Python packages installed" -ForegroundColor Green

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  ✅ Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart your computer (required for Docker)" -ForegroundColor White
Write-Host "2. Open Docker Desktop and let it start" -ForegroundColor White
Write-Host "3. Run: cd C:\Projects\odyssey-v2" -ForegroundColor White
Write-Host "4. Continue with infrastructure setup" -ForegroundColor White
Write-Host ""
