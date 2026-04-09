# Start Odyssey Infrastructure Services

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  Starting Odyssey Services" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "Docker is running" -ForegroundColor Green
} catch {
    Write-Host "Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Navigate to docker directory
Set-Location "D:\Projects\odyssey-v2\infrastructure\docker"

# Start services
Write-Host ""
Write-Host "Starting infrastructure services..." -ForegroundColor Yellow
docker-compose -f docker-compose.dev.yml up -d

# Wait for services to be ready
Write-Host ""
Write-Host "Waiting for services to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Check service status
Write-Host ""
Write-Host "Service Status:" -ForegroundColor Yellow
docker-compose -f docker-compose.dev.yml ps

# Show access URLs
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Services Started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Access your services at:" -ForegroundColor Yellow
Write-Host "  QuestDB Console:  http://localhost:9000" -ForegroundColor White
Write-Host "  Redis:            localhost:6379" -ForegroundColor White
Write-Host "  Kafka:            localhost:9092" -ForegroundColor White
Write-Host "  Kafka UI:         http://localhost:8080" -ForegroundColor White
Write-Host "  Prometheus:       http://localhost:9090" -ForegroundColor White
Write-Host "  Grafana:          http://localhost:3000" -ForegroundColor White
Write-Host "     Username: admin" -ForegroundColor Gray
Write-Host "     Password: admin" -ForegroundColor Gray

Write-Host ""
Write-Host "To stop services, run:" -ForegroundColor Yellow
Write-Host "  docker-compose -f infrastructure/docker/docker-compose.dev.yml down" -ForegroundColor White
Write-Host ""
