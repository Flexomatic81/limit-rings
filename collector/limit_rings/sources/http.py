"""HTTP fetching for authenticated requests: get JSON, always refuse redirects."""

import json
import os
import ssl
import urllib.error
import urllib.request

from ..version import VERSION


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib keeps Authorization on redirects, even to foreign hosts – so allow none at all."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


# The Python from python.org ships without root certificates until its "Install Certificates" script has run;
# macOS itself always has a bundle here.
_SYSTEM_BUNDLE = "/etc/ssl/cert.pem"


def _tls_context(make=ssl.create_default_context, bundle: str = _SYSTEM_BUNDLE):
    ctx = make()
    if not ctx.cert_store_stats()["x509_ca"] and os.path.isfile(bundle):
        ctx.load_verify_locations(cafile=bundle)
    return ctx


_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_tls_context()))


def get_json(url: str, headers: dict, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": f"limit-rings/{VERSION}",
                                               **headers})
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.load(resp)
