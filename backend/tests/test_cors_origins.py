from app.main import FlexibleCORSMiddleware


def _middleware() -> FlexibleCORSMiddleware:
    return FlexibleCORSMiddleware(
        app=lambda scope, receive, send: None,
        allowed_origins=["http://localhost:5175", "http://127.0.0.1:5175"],
    )


def test_credentialed_cors_accepts_explicit_loopback_origin():
    middleware = _middleware()

    assert middleware._is_allowed("http://127.0.0.1:5175") is True


def test_credentialed_cors_rejects_unconfigured_tunnel_origin():
    middleware = _middleware()

    assert middleware._is_allowed("https://attacker.trycloudflare.com") is False
