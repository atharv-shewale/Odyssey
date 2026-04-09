Write-Host "Diagnosing Docker Setup..." -ForegroundColor Yellow
Write-Host ""

# 1. Check Docker daemon
Write-Host "1. Docker Daemon:" -ForegroundColor Cyan
try {
    docker info 2>&1 | Select-String "Server Version"
} catch {
    Write-Host "   ❌ Docker daemon not running or not found" -ForegroundColor Red
}

# 2. Check disk space
Write-Host "`n2. Docker Disk Space:" -ForegroundColor Cyan
try {
    docker system df
} catch {
    Write-Host "   ❌ Unable to retrieve disk usage" -ForegroundColor Red
}

# 3. Check networks
Write-Host "`n3. Docker Networks:" -ForegroundColor Cyan
try {
    docker network ls
} catch {
    Write-Host "   ❌ Unable to list networks" -ForegroundColor Red
}

# 4. Check volumes
Write-Host "`n4. Docker Volumes:" -ForegroundColor Cyan
try {
    docker volume ls
} catch {
    Write-Host "   ❌ Unable to list volumes" -ForegroundColor Red
}

# 5. Check running containers
Write-Host "`n5. Running Containers:" -ForegroundColor Cyan
try {
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
} catch {
    Write-Host "   ❌ Unable to list running containers" -ForegroundColor Red
}

# 6. Check for port conflicts
Write-Host "`n6. Port Usage Check:" -ForegroundColor Cyan
Write-Host "Checking if ports are available..."
$ports = @(9000, 6379, 9092, 8080, 9090, 3000)
foreach ($port in $ports) {
    $result = netstat -ano | findstr ":$port "
    if ($result) {
        Write-Host "   Port $port is in use" -ForegroundColor Yellow
    } else {
        Write-Host "   Port $port is available" -ForegroundColor Green
    }
}

# 7. Docker Compose Version
Write-Host "`n7. Docker Compose Version:" -ForegroundColor Cyan
try {
    docker-compose version
} catch {
    Write-Host "   ❌ Docker Compose not found" -ForegroundColor Red
}
