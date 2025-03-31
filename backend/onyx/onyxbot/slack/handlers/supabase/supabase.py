"""
Supabase Logger Module

This module provides functionality to log successful bot responses to Supabase
using direct API calls instead of the Supabase SDK.
"""

import requests
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from onyx.utils.logger import logger

import os


class SupabaseLogger:
    """Logger class for sending successful bot responses to Supabase"""
    
    # TODO: Replace config with AWS Secrets Handler
    
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.api_key = os.getenv("SUPABASE_KEY")
        self.auth_email = os.getenv("SUPABASE_AUTH_EMAIL")
        self.auth_password = os.getenv("SUPABASE_AUTH_PASSWORD")
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        
    # def __init__(self, config: NHSPolicyConfig):
    #     """Initialize Supabase logger with configuration

    #     Args:
    #         config: Application configuration containing Supabase credentials
    #     """
    #     self.url = config.supabase_url
    #     self.api_key = config.supabase_api_key
    #     self.auth_email = config.supabase_auth_email
    #     self.auth_password = config.supabase_auth_password
    #     self.access_token = None
    #     self.refresh_token = None
    #     self.expires_at = None

    def _get_valid_token(self) -> str:
        """Get a valid access token, refreshing if needed

        Returns:
            str: Valid access token
        """
        # If no token exists, authenticate
        if not self.access_token:
            self._authenticate()
            return self.access_token

        # If token is expired and we have refresh token, try refresh
        current_time = int(datetime.now(timezone.utc).timestamp())
        if self.expires_at and current_time >= self.expires_at and self.refresh_token:
            try:
                self._refresh_token()
                return self.access_token
            except Exception as e:
                logger.warning(
                    f"Token refresh failed, falling back to full auth: {str(e)}")
                self._authenticate()
                return self.access_token

        # If token is expired but no refresh token, authenticate
        if self.expires_at and current_time >= self.expires_at:
            self._authenticate()
            return self.access_token

        return self.access_token

    def _refresh_token(self) -> None:
        """Refresh access token using refresh token"""
        try:
            response = requests.post(
                f"{self.url}/auth/v1/token?grant_type=refresh_token",
                headers={
                    "apikey": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "refresh_token": self.refresh_token
                }
            )
            response.raise_for_status()

            data = response.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.expires_at = int(datetime.now(
                timezone.utc).timestamp()) + data.get("expires_in", 3600)
            logger.info("Successfully refreshed Supabase token")

        except Exception as e:
            logger.error(f"Supabase token refresh failed: {str(e)}")
            if hasattr(response, 'text'):
                logger.debug(f"Refresh response: {response.text}")
            raise

    def _authenticate(self) -> None:
        """Authenticate with Supabase using email/password"""
        try:
            response = requests.post(
                f"{self.url}/auth/v1/token?grant_type=password",
                headers={
                    "apikey": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "email": self.auth_email,
                    "password": self.auth_password
                }
            )
            response.raise_for_status()

            data = response.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.expires_at = int(datetime.now(
                timezone.utc).timestamp()) + data.get("expires_in", 3600)
            logger.info("Successfully authenticated with Supabase")

        except Exception as e:
            logger.error(f"Supabase authentication failed: {str(e)}")
            if hasattr(response, 'text'):
                logger.debug(f"Auth response: {response.text}")
            raise

    def log_success(self,
                    user_id: str,
                    channel_id: str,
                    thread_id: str,
                    user_message: str,
                    response_text: str,
                    request_time: datetime,
                    response_time: datetime,
                    bot_id: str,
                    bot_name: str,
                    system_prompt: str,
                    input_attachments: Optional[Dict] = None,
                    chat_history_length: Optional[int] = None,
                    output_attachments: Optional[Dict] = None) -> None:
        """Log successful bot response to Supabase

        Args:
            user_id: ID of the user who sent the message
            channel_id: ID of the channel where the message was sent
            thread_id: ID of the thread if message was in thread
            user_message: Original message from user
            response_text: Bot's response text
            request_time: When the request was received
            response_time: When the response was sent
            bot_id: Bot's unique identifier
            bot_name: Type/name of the bot
            system_prompt: System prompt used
            input_attachments: Any attachments in user's message
            chat_history_length: Length of chat history
            output_attachments: Any attachments in bot's response
        """
        # Prepare log entry
        log_entry = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request_timestamp": request_time.isoformat(),
            "response_timestamp": response_time.isoformat(),
            "bot_id": bot_id,
            "type_of_bot": bot_name,
            "user_id": user_id,
            "channel_id": channel_id,
            "thread_id": thread_id,
            "user_message": user_message,
            "input_attachments": input_attachments or {},
            "system_prompt": system_prompt,
            "chat_history_length": chat_history_length or 0,
            "response_text": response_text,
            "duration": (response_time - request_time).total_seconds(),
            "output_attachments": output_attachments or {}
        }

        try:
            # Try to insert log entry
            self._insert_log(log_entry)

        except Exception as e:
            # If first attempt fails, try to get a new valid token once
            logger.info("Log insert failed, attempting to get new token")
            try:
                self.access_token = None  # Force new token
                self._insert_log(log_entry)

            except Exception as e:
                # Log error but don't raise - we don't want logging failures to affect the bot
                logger.error(
                    f"Failed to log to Supabase after token refresh: {str(e)}")
                logger.debug("Failed log entry: %s", log_entry)

    def _insert_log(self, log_entry: Dict[str, Any]) -> None:
        """Insert a log entry into Supabase

        Args:
            log_entry: The log entry to insert
        """
        # Get valid token
        token = self._get_valid_token()

        response = requests.post(
            f"{self.url}/rest/v1/bot_logs",
            headers={
                "apikey": self.api_key,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json=log_entry
        )

        response.raise_for_status()
        logger.info("Successfully logged bot response to Supabase")
