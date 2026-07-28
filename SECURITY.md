# Security

- TLS verification is required for acquisition.
- No authentication bypass, CAPTCHA bypass, or credential stuffing.
- Secrets must not appear in logs.
- `data/**` is local-only and must never be published.
- Optional UI binds to `127.0.0.1` only.
