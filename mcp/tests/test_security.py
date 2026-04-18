"""Tests for security.py (v2.6.0, #09)."""

import os

import pytest

from samvil_mcp.security import (
    detect_dangerous,
    sanitize_filename,
    validate_path_within,
    validate_url_safe,
)


# ── sanitize_filename ─────────────────────────────────────────


def test_sanitize_filename_normal():
    assert sanitize_filename("my-project") == "my-project"


def test_sanitize_filename_strips_path_traversal():
    result = sanitize_filename("../etc/passwd")
    assert ".." not in result
    assert "/" not in result
    assert "etcpasswd" in result


def test_sanitize_filename_limits_length():
    long_name = "a" * 200
    assert len(sanitize_filename(long_name)) == 64


def test_sanitize_filename_empty_becomes_unnamed():
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename("!@#$%") == "unnamed"


def test_sanitize_filename_custom_max():
    assert len(sanitize_filename("abcdefgh", max_len=4)) == 4


# ── validate_path_within ──────────────────────────────────────


def test_path_within_root(tmp_path):
    child = tmp_path / "sub" / "file.txt"
    valid, _ = validate_path_within(child, tmp_path)
    assert valid


def test_path_escapes_root(tmp_path):
    escape = tmp_path / ".." / ".." / "etc" / "passwd"
    valid, msg = validate_path_within(escape, tmp_path)
    assert not valid
    assert "escapes" in msg


def test_path_exact_root(tmp_path):
    valid, _ = validate_path_within(tmp_path, tmp_path)
    assert valid


# ── validate_url_safe ─────────────────────────────────────────


def test_valid_https():
    valid, _ = validate_url_safe("https://example.com/api")
    assert valid


def test_block_localhost():
    valid, _ = validate_url_safe("http://localhost/admin")
    assert not valid


def test_block_localhost_with_env(monkeypatch):
    monkeypatch.setenv("SAMVIL_ALLOW_LOCAL_TRANSPORT", "1")
    valid, _ = validate_url_safe("http://localhost/dev")
    assert valid


def test_block_private_ip():
    valid, _ = validate_url_safe("http://10.0.0.1/")
    assert not valid


def test_block_link_local():
    valid, _ = validate_url_safe("http://169.254.169.254/latest")
    assert not valid


def test_block_file_scheme():
    valid, _ = validate_url_safe("file:///etc/passwd")
    assert not valid


def test_block_userinfo():
    valid, _ = validate_url_safe("http://user:pass@evil.com")
    assert not valid


def test_block_empty_hostname():
    valid, _ = validate_url_safe("http:///path")
    assert not valid


def test_block_reserved_ip():
    valid, _ = validate_url_safe("http://0.0.0.0/")
    assert not valid


# ── detect_dangerous ──────────────────────────────────────────


def test_detect_path_traversal():
    assert "../" in detect_dangerous("../../etc/passwd")


def test_detect_eval():
    assert "eval(" in detect_dangerous("eval('bad')")


def test_detect_subprocess():
    assert "subprocess" in detect_dangerous("import subprocess")


def test_clean_string():
    assert detect_dangerous("hello world") == []
