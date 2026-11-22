"""
CAD MCP package
"""

import os
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('cad_mcp')

# Load configuration
def load_config():
    """Load the configuration file."""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info("Configuration file loaded successfully")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration file: {str(e)}")
        # Return the default configuration.
        return {
            "server": {
                "name": "CAD MCP Server",
                "version": "1.0.0",
                "host": "0.0.0.0",
                "port": 5000,
                "debug": True
            },
            "cad": {
                "type": "AUTOCAD",
                "startup_wait_time": 20,
                "command_delay": 0.5
            },
            "output": {
                "directory": "output",
                "default_filename": "cad_drawing.dwg"
            }
        }

# Export configuration
config = load_config()

__all__ = [
    'config'
]
