"""
Langfuse Logger Module

This module provides functionality to log successful bot responses to Langfuse
using direct API calls instead of the Langfuse SDK.
"""

import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from onyx.utils.logger import logger