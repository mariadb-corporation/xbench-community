# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging

from slack import WebClient
from slack.errors import SlackApiError

from .exceptions import SlackClientException


class SlackClient:
    """
    Class to notify channel
    """
    # https://python-slackclient.readthedocs.io/en/1.0.3/auth.html
    def __init__(self, slack_channel, slack_token, **kwargs):
        self.slack_channel = slack_channel or kwargs.get("slack_channel")
        self.slack_token = slack_token or kwargs.get("slack_token")
        self.logger = logging.getLogger(__name__)
        self.wc = WebClient(self.slack_token)

    def send_text(self, message):
        """
        Post message
        """

        try:
            response = self.wc.chat_postMessage(
                channel=self.slack_channel, text=message
            )
            self.logger.info(
                f"Message successfully posted to channel {self.slack_channel}"
            )

        except SlackApiError as e:
            error_message = e.response.get("error")
            raise SlackClientException(
                f"an error occurred during sending message to Slack: {error_message}. Details: {e.response}"
            )

    def send_blocks(self, blocks):
        """
        Post blocks. See Block Kit Builder
        https://api.slack.com/tools/block-kit-builder

        ToDo:
        color = '#f44242' // Red
        color = '#ff8316' // Yellow
        attachments: [[
                    color: color,
                    blocks: blocks
                 ]]

        """

        try:
            response = self.wc.chat_postMessage(
                channel=self.slack_channel, blocks=blocks
            )
            self.logger.info(
                f"Message successfully posted to channel {self.slack_channel}"
            )

        except SlackApiError as e:
            error_message = e.response.get("error")
            raise SlackClientException(
                f"an error occurred during sending message to Slack: {error_message}. Details: {e.response}"
            )
