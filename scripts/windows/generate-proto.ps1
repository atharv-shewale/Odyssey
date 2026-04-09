Write-Host "Generating Protobuf Code..." -ForegroundColor Cyan

$root = "D:\Projects\odyssey-v2"
cd $root

# Install Python deps
Write-Host "Installing Python deps..." -ForegroundColor Yellow
pip install -q grpcio grpcio-tools protobuf

# Create directories
New-Item -ItemType Directory -Path "shared\python\proto" -Force | Out-Null
New-Item -ItemType Directory -Path "shared\nodejs\proto" -Force | Out-Null

# Python generation
Write-Host "Generating Python..." -ForegroundColor Yellow
python -m grpc_tools.protoc -I shared/proto --python_out=shared/python/proto --grpc_python_out=shared/python/proto shared/proto/trading.proto
python -m grpc_tools.protoc -I shared/proto --python_out=shared/python/proto --grpc_python_out=shared/python/proto shared/proto/ml.proto
python -m grpc_tools.protoc -I shared/proto --python_out=shared/python/proto --grpc_python_out=shared/python/proto shared/proto/strategy.proto
New-Item -ItemType File -Path "shared\python\proto\__init__.py" -Force | Out-Null

# Node.js generation
Write-Host "Generating Node.js..." -ForegroundColor Yellow
npx grpc_tools_node_protoc --js_out=import_style=commonjs,binary:shared/nodejs/proto --grpc_out=grpc_js:shared/nodejs/proto -I shared/proto shared/proto/trading.proto
npx grpc_tools_node_protoc --js_out=import_style=commonjs,binary:shared/nodejs/proto --grpc_out=grpc_js:shared/nodejs/proto -I shared/proto shared/proto/ml.proto
npx grpc_tools_node_protoc --js_out=import_style=commonjs,binary:shared/nodejs/proto --grpc_out=grpc_js:shared/nodejs/proto -I shared/proto shared/proto/strategy.proto

# Count files
$pyFiles = (Get-ChildItem "shared\python\proto" -File).Count
$jsFiles = (Get-ChildItem "shared\nodejs\proto" -File).Count

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host "Python: $pyFiles files" -ForegroundColor White
Write-Host "Node.js: $jsFiles files" -ForegroundColor White
