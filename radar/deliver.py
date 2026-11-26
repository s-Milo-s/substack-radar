"""Print the digest, and post it to Slack if SLACK_WEBHOOK_URL is set (never in --dry-run).

Slack is the only outbound destination. Nothing here talks to Substack.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request

log = logging.getLogger("radar.deliver")


def send(markdown: str, dry_run: bool = False) -> None:
    print(markdown)
    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if dry_run or not hook:
        if not dry_run:
            log.info("SLACK_WEBHOOK_URL not set; printed only")
        return
    body = json.dumps({"text": markdown}).encode()
    req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:  # a Slack outage shouldn't fail the run
        log.error("Slack post failed: %s", e)
