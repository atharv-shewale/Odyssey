/**
 * gRPC Proto Loader for Node.js Services
 * Loads .proto files at runtime (no pre-generation needed)
 */

const grpc = require('@grpc/grpc-js');
const protoLoaderLib = require('@grpc/proto-loader');
const path = require('path');

class ProtoLoader {
    constructor() {
        this.protoPath = path.join(__dirname, '../../proto');
        this.packageDefinitions = {};
        this.protos = {};
    }

    /**
     * Load a proto file
     * @param {string} protoFile - Name of proto file (e.g., 'trading.proto')
     * @param {string} packageName - Package name (e.g., 'trading')
     */
    loadProto(protoFile, packageName) {
        const protoFilePath = path.join(this.protoPath, protoFile);
        
        const packageDefinition = protoLoaderLib.loadSync(protoFilePath, {
            keepCase: true,
            longs: String,
            enums: String,
            defaults: true,
            oneofs: true
        });

        this.packageDefinitions[packageName] = packageDefinition;
        this.protos[packageName] = grpc.loadPackageDefinition(packageDefinition)[packageName];
        
        return this.protos[packageName];
    }

    /**
     * Load all Odyssey proto files
     */
    loadAll() {
        this.loadProto('trading.proto', 'trading');
        this.loadProto('ml.proto', 'ml');
        this.loadProto('strategy.proto', 'strategy');
        
        console.log('✅ All proto files loaded');
        return this.protos;
    }

    /**
     * Get loaded proto by package name
     */
    getProto(packageName) {
        return this.protos[packageName];
    }

    /**
     * Create gRPC client
     * @param {string} packageName - Package name (e.g., 'trading')
     * @param {string} serviceName - Service name (e.g., 'TradingService')
     * @param {string} address - Server address (e.g., 'localhost:50051')
     */
    createClient(packageName, serviceName, address) {
        if (!this.protos[packageName]) {
            throw new Error(`Proto package '${packageName}' not loaded`);
        }

        const ServiceClient = this.protos[packageName][serviceName];
        return new ServiceClient(address, grpc.credentials.createInsecure());
    }

    /**
     * Create gRPC server
     */
    createServer() {
        return new grpc.Server();
    }
}

// Export singleton instance with different variable name to avoid conflict
const loader = new ProtoLoader();

module.exports = {
    protoLoader: loader,
    grpc,
    ProtoLoader
};
