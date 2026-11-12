"""Personal-Gmail '+' alias mode and Google OAuth tokens on /mcp."""
import pytest

from app.services import oauth
from app.services.errors import Forbidden
from app.services.workspace import Draft, LocalWorkspace, addr_intake, addr_lecturer


def test_plus_alias_addresses_and_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DEMO_INBOX", "demo.owner@gmail.com")
    assert addr_lecturer("MZD") == "demo.owner+lect-mzd@gmail.com"
    assert addr_intake("UCDF2505DSM(ANM)", "G1") == "demo.owner+ucdf2505dsm-anm-g1@gmail.com"
    ws = LocalWorkspace(tmp_path)
    ws.create_drafts("x", [Draft(to=[addr_lecturer("MZD")], bcc=[], subject="s", body="b")])
    with pytest.raises(Forbidden):
        ws.create_drafts("x", [Draft(to=["someone.else@gmail.com"], bcc=[], subject="s", body="b")])
    with pytest.raises(Forbidden):
        ws.create_drafts("x", [Draft(to=["demo.ownerX+a@gmail.com"], bcc=[], subject="s", body="b")])


def test_google_oauth_token_verification(monkeypatch):
    monkeypatch.setenv("MCP_GOOGLE_CLIENT_IDS", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("MCP_ALLOWED_EMAILS", "demo.owner@gmail.com")
    oauth._cache.clear()
    good = lambda t: {"aud": "abc.apps.googleusercontent.com", "email": "demo.owner@gmail.com", "expires_in": 300}
    assert oauth.verify("t1", fetch=good) == "demo.owner@gmail.com"
    assert oauth.verify("t2", fetch=lambda t: {"aud": "other", "email": "demo.owner@gmail.com"}) is None
    assert oauth.verify("t3", fetch=lambda t: {"aud": "abc.apps.googleusercontent.com", "email": "x@gmail.com"}) is None
    monkeypatch.delenv("MCP_GOOGLE_CLIENT_IDS")
    assert oauth.verify("t4", fetch=good) is None
