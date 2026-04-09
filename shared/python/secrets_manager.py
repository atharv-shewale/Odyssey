"""
Odyssey v2 - Enterprise Secrets Manager
Replaces insecure .env plaintext files. Connects to HashiCorp Vault or AWS Secrets Manager.
(Fallback to Python keyring for local bare-metal deployments).
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger('secrets-manager')

class SecretsManager:
    """
    Centralized secret retrieval to prevent hardcoded credentials or plain .env usage
    in production environments.
    """
    
    def __init__(self, provider: str = "local"):
        self.provider = provider
        
        if self.provider == "aws":
            import boto3
            self.client = boto3.client('secretsmanager', region_name='ap-south-1')
        elif self.provider == "vault":
            import hvac
            self.client = hvac.Client(url=os.environ.get('VAULT_ADDR'))
        else:
            self.client = None

    def get_secret(self, secret_name: str) -> Optional[str]:
        """Fetch a secret securely based on the active provider."""
        
        try:
            if self.provider == "aws":
                response = self.client.get_secret_value(SecretId=secret_name)
                return response.get('SecretString')
                
            elif self.provider == "vault":
                response = self.client.secrets.kv.v2.read_secret_version(path=secret_name)
                return response['data']['data'].get('value')
                
            else:
                # Local Keyring fallback
                import keyring
                # Typically format 'system_name', 'username'
                val = keyring.get_password("odyssey_v2", secret_name)
                
                # Ultimate fallback to generic env if missing in dev
                if not val:
                    val = os.getenv(secret_name)
                return val
                
        except Exception as e:
            logger.error(f"Failed to retrieve secret {secret_name} from {self.provider}: {e}")
            return None

# Singleton instance
vault = SecretsManager(provider=os.getenv("SECRETS_PROVIDER", "local"))

def get_secret(name: str) -> str:
    return vault.get_secret(name)
