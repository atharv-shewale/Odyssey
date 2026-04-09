# Verify Odyssey Setup

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  Verifying Odyssey Setup" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# 1. Check Docker
Write-Host "1. Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "   Docker is running" -ForegroundColor Green
} catch {
    Write-Host "   Docker is not running" -ForegroundColor Red
    $allGood = $false
}

# 2. Check QuestDB
Write-Host ""
Write-Host "2. Checking QuestDB..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9000" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "   QuestDB is accessible" -ForegroundColor Green
    }
} catch {
    Write-Host "   QuestDB is not accessible" -ForegroundColor Red
    $allGood = $false
}

# 3. Check Redis
Write-Host ""
Write-Host "3. Checking Redis..." -ForegroundColor Yellow
try {
    $redisTest = docker exec odyssey-redis redis-cli ping
    if ($redisTest -eq "PONG") {
        Write-Host "   Redis is responding" -ForegroundColor Green
    }
} catch {
    Write-Host "   Redis is not responding" -ForegroundColor Red
    $allGood = $false
}

# 4. Check Kafka
Write-Host ""
Write-Host "4. Checking Kafka UI..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "   Kafka UI is accessible" -ForegroundColor Green
    }
} catch {
    Write-Host "   Kafka UI is not accessible" -ForegroundColor Red
    $allGood = $false
}

# 5. Check Prometheus
Write-Host ""
Write-Host "5. Checking Prometheus..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9090" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "   Prometheus is accessible" -ForegroundColor Green
    }
} catch {
    Write-Host "   Prometheus is not accessible" -ForegroundColor Red
    $allGood = $false
}

# 6. Check Grafana
Write-Host ""
Write-Host "6. Checking Grafana..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "   Grafana is accessible" -ForegroundColor Green
    }
} catch {
    Write-Host "   Grafana is not accessible" -ForegroundColor Red
    $allGood = $false
}

# 7. Check Node.js
Write-Host ""
Write-Host "7. Checking Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "   Node.js $nodeVersion installed" -ForegroundColor Green
} catch {
    Write-Host "   Node.js not found" -ForegroundColor Red
    $allGood = $false
}

# 8. Check Python
Write-Host ""
Write-Host "8. Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version
    Write-Host "   Python $pythonVersion installed" -ForegroundColor Green
} catch {
    Write-Host "   Python not found" -ForegroundColor Red
    $allGood = $false
}

# Final verdict
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan

if ($allGood) {
    Write-Host "  ALL SYSTEMS GO!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "You are ready to start development." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next: Initialize Git and create shared components." -ForegroundColor Yellow
} else {
    Write-Host "  SOME ISSUES DETECTED" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Please fix the issues above before continuing." -ForegroundColor Yellow
}

Write-Host ""
