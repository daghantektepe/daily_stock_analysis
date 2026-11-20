# -*- coding: utf-8 -*-
"""
===================================
Notification sender layer
===================================

Lazy-exported notification channel senders (PEP 562) so importing helper
functions from lightweight senders (e.g. gotify/ntfy) does not eagerly load
heavy optional SDKs like ``lark_oapi`` during API startup.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Tuple

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "AstrbotSender": (".astrbot_sender", "AstrbotSender"),
    "CustomWebhookSender": (".custom_webhook_sender", "CustomWebhookSender"),
    "DiscordSender": (".discord_sender", "DiscordSender"),
    "EmailSender": (".email_sender", "EmailSender"),
    "FeishuSender": (".feishu_sender", "FeishuSender"),
    "GotifySender": (".gotify_sender", "GotifySender"),
    "resolve_gotify_message_endpoint": (".gotify_sender", "resolve_gotify_message_endpoint"),
    "NtfySender": (".ntfy_sender", "NtfySender"),
    "resolve_ntfy_endpoint": (".ntfy_sender", "resolve_ntfy_endpoint"),
    "PushoverSender": (".pushover_sender", "PushoverSender"),
    "PushplusSender": (".pushplus_sender", "PushplusSender"),
    "Serverchan3Sender": (".serverchan3_sender", "Serverchan3Sender"),
    "SlackSender": (".slack_sender", "SlackSender"),
    "TelegramSender": (".telegram_sender", "TelegramSender"),
    "WechatSender": (".wechat_sender", "WechatSender"),
    "WECHAT_IMAGE_MAX_BYTES": (".wechat_sender", "WECHAT_IMAGE_MAX_BYTES"),
    "DingtalkSender": (".dingtalk_sender", "DingtalkSender"),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(_EXPORTS.keys()))
