from samvil_mcp.event_sanitizer import sanitize_event_data, sanitize_event_label


def test_event_data_redacts_nested_prompt_credentials_and_email() -> None:
    payload = {
        "app": "Build a private tool for person@example.com",
        "nested": {
            "token": "fixture-secret-token",
            "note": "contact person@example.com with api_key=fixture-value",
        },
    }

    sanitized = sanitize_event_data(payload)

    serialized = str(sanitized)
    assert sanitized["app"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert "person@example.com" not in serialized
    assert "fixture-value" not in serialized


def test_event_label_rejects_arbitrary_sensitive_prose() -> None:
    assert sanitize_event_label("build_pass") == "build_pass"
    assert (
        sanitize_event_label("private person@example.com token=fixture-secret")
        == "redacted_event_type"
    )
