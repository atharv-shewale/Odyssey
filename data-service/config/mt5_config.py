"""
MT5 Configuration — loaded from environment variables
"""
import os
from dotenv import load_dotenv

load_dotenv()

MT5_CONFIG = {
    'login': int(os.getenv('MT5_LOGIN', '0')),
    'password': os.getenv('MT5_PASSWORD', ''),
    'server': os.getenv('MT5_SERVER', 'MetaQuotes-Demo'),
}

# Set to None to use the currently logged-in account
if not MT5_CONFIG['login']:
    MT5_CONFIG = None
