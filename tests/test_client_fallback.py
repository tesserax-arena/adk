"""The ADK must keep working when tesserax.net does not.

The default base URL is the public domain behind Cloudflare. When Cloudflare
challenges the client, fails at the edge (e.g. 525 after the origin
certificate lapses), or the domain cannot be connected to, the client switches
to the Fly origin once and carries on.
"""

import httpx
import pytest

from tesserax_adk.client import FALLBACK_ORIGIN, ArenaClient, ArenaError

APEX = "https://tesserax.net"
VERSION = {"version": 1}


def client_with(handler, base=APEX):
    hops = []

    def on_fallback(old, new):
        hops.append((old, new))

    c = ArenaClient(base, transport=httpx.MockTransport(handler), on_fallback=on_fallback)
    return c, hops


def origin_ok(request):
    if request.url.host == "tesserax-arena.fly.dev":
        return httpx.Response(200, json=VERSION)
    return None


def test_cloudflare_525_falls_back_to_the_origin():
    def handler(request):
        return origin_ok(request) or httpx.Response(
            525, text="error code: 525", headers={"server": "cloudflare", "content-type": "text/plain"}
        )

    c, hops = client_with(handler)
    assert c.version() == VERSION
    assert c.base_url == FALLBACK_ORIGIN and hops == [(APEX, FALLBACK_ORIGIN)]


def test_connection_failure_falls_back_to_the_origin():
    def handler(request):
        if origin_ok(request):
            return origin_ok(request)
        raise httpx.ConnectError("TLS handshake failed", request=request)

    c, _ = client_with(handler)
    assert c.version() == VERSION
    assert c.used_fallback


def test_bot_challenge_still_falls_back():
    def handler(request):
        return origin_ok(request) or httpx.Response(
            403, text="<html>Just a moment...</html>", headers={"content-type": "text/html"}
        )

    c, _ = client_with(handler)
    assert c.version() == VERSION


def test_a_read_timeout_is_never_retried_elsewhere():
    """The request may have reached the server; retrying could duplicate it."""
    seen = []

    def handler(request):
        seen.append(request.url.host)
        raise httpx.ReadTimeout("slow", request=request)

    c, _ = client_with(handler)
    with pytest.raises(httpx.ReadTimeout):
        c.register_account()
    assert seen == ["tesserax.net"]


def test_an_origin_5xx_without_cloudflare_is_a_real_error():
    """A 500 from the app itself is not an edge failure: report it, don't hop."""
    def handler(request):
        return httpx.Response(502, text="bad gateway", headers={"server": "fly"})

    c, hops = client_with(handler)
    with pytest.raises(ArenaError):
        c.version()
    assert hops == [] and c.base_url == APEX


def test_a_custom_base_url_never_falls_back():
    def handler(request):
        return httpx.Response(525, text="error code: 525", headers={"server": "cloudflare"})

    c, hops = client_with(handler, base="https://my-own-arena.example")
    with pytest.raises(ArenaError):
        c.version()
    assert hops == []
