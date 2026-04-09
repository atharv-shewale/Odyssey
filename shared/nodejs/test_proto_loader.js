/**
 * Test Proto Loader
 */

const { protoLoader } = require('./proto/protoLoader');
const path = require('path');
const fs = require('fs');

console.log('Testing Proto Loader...\n');

// Debug: Check proto path
const protoPath = path.join(__dirname, '../proto');
console.log('Proto path:', protoPath);
console.log('Proto path exists:', fs.existsSync(protoPath));

if (fs.existsSync(protoPath)) {
    const files = fs.readdirSync(protoPath);
    console.log('Files in proto directory:', files);
} else {
    console.error('❌ Proto directory does not exist!');
    process.exit(1);
}

console.log('\nLoading proto files...\n');

try {
    // Load all proto files
    const protos = protoLoader.loadAll();
    
    // Check trading proto
    console.log('✅ Trading proto loaded');
    console.log('   Services:', Object.keys(protos.trading));
    
    // Check ML proto
    console.log('✅ ML proto loaded');
    console.log('   Services:', Object.keys(protos.ml));
    
    // Check strategy proto
    console.log('✅ Strategy proto loaded');
    console.log('   Services:', Object.keys(protos.strategy));
    
    
    console.log('\n✅ All proto files loaded successfully!');
    
} catch (error) {
    console.error('❌ Error loading protos:', error.message);
    console.error('Stack trace:', error.stack);
}
