from samvil_mcp.event_sanitizer import (
    sanitize_event_data,
    sanitize_event_label,
    sanitize_stage_label,
)


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
    assert sanitize_event_label("ghp_fixture_secret") == "redacted_event_type"
    assert (
        sanitize_event_label("private person@example.com token=fixture-secret")
        == "redacted_event_type"
    )


def test_event_data_redacts_camel_case_keys_and_unlabelled_tokens() -> None:
    github_pat = "github_pat_" + "A" * 82
    payload = {
        "accessToken": "-".join(("fixture", "access", "token")),
        "userPassword": "-".join(("fixture", "password")),
        "nested": {"note": f"ghp_fixture_secret {github_pat}"},
    }

    sanitized = sanitize_event_data(payload)

    assert sanitized["accessToken"] == "[REDACTED]"
    assert sanitized["userPassword"] == "[REDACTED]"
    assert "ghp_fixture_secret" not in str(sanitized)
    assert github_pat not in str(sanitized)


def test_event_data_redacts_credentials_embedded_in_plain_strings() -> None:
    secrets = {
        "access": "-".join(("access", "fixture", "value")),
        "client": "-".join(("client", "fixture", "value")),
        "basic": "".join(("QWxh", "ZGRp", "bjpvcGVu", "IHNlc2FtZQ==")),
        "cookie": "-".join(("session", "fixture", "value")),
    }
    payload = {
        "note": (
            f"access_token={secrets['access']} "
            f"client_secret={secrets['client']} "
            f"Authorization: Basic {secrets['basic']} "
            f"Cookie: session={secrets['cookie']}"
        )
    }

    serialized = str(sanitize_event_data(payload))

    assert all(secret not in serialized for secret in secrets.values())
    assert serialized.count("[REDACTED") >= 3


def test_event_data_redacts_quoted_json_and_any_authorization_scheme() -> None:
    secrets = {
        "access": "-".join(("json", "access", "value")),
        "client": "-".join(("json", "client", "value")),
        "credential": "".join(("AKIA", "FIXTURE", "CREDENTIAL")),
        "signature": "".join(("dead", "beef", "fixture")),
    }
    payload = {
        "note": (
            '{"access_token":"'
            + secrets["access"]
            + '","client_secret":"'
            + secrets["client"]
            + '","Authorization":"AWS4-HMAC-SHA256 Credential='
            + secrets["credential"]
            + ", Signature="
            + secrets["signature"]
            + '"}'
        )
    }

    serialized = str(sanitize_event_data(payload))

    assert all(secret not in serialized for secret in secrets.values())


def test_stage_label_rejects_arbitrary_sensitive_prose() -> None:
    assert sanitize_stage_label("qa") == "qa"
    assert sanitize_stage_label("ghp_fixture_secret") == "redacted_stage"
    assert (
        sanitize_stage_label("person@example.com token=fixture-secret")
        == "redacted_stage"
    )
