# Paths
$protoPath = "D:\Projects\odyssey-v2\shared\proto"
$nodejsOut = "D:\Projects\odyssey-v2\shared\nodejs\proto"
$protoFiles = @("trading.proto", "ml.proto", "strategy.proto")

# Create output directory if it doesn't exist
New-Item -ItemType Directory -Path $nodejsOut -Force | Out-Null

# Plugin path (use .exe instead of .cmd for Windows)
$pluginPath = "$env:APPDATA\npm\node_modules\grpc-tools\bin\grpc_node_plugin.exe"

# Generate Node.js code
Write-Host "Generating Node.js gRPC code..." -ForegroundColor Yellow

foreach ($file in $protoFiles) {
    Write-Host "Processing $file..." -ForegroundColor Gray
    
    & "$env:APPDATA\npm\node_modules\grpc-tools\bin\grpc_tools_node_protoc.cmd" `
        --js_out="import_style=commonjs,binary:$nodejsOut" `
        --grpc_out="grpc_js:$nodejsOut" `
        --plugin="protoc-gen-grpc=$pluginPath" `
        -I "$protoPath" `
        "$protoPath\$file"
}

Write-Host "✅ Node.js code generated at $nodejsOut" -ForegroundColor Green
