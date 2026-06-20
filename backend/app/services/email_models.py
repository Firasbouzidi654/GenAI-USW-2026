"""Shared data shape returned by every email provider (IMAP, Microsoft Graph, ...)."""

from dataclasses import dataclass


@dataclass
class FetchedEmail:
    subject: str
    sender: str
    date: str
    body: str
    snippet: str
