"""HTTP fetching for authenticated requests: get JSON, always refuse redirects."""

import json
import urllib.error
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib keeps Authorization on redirects, even to foreign hosts – so allow none at all."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def get_json(url: str, headers: dict, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "limit-rings/0.2",
                                               **headers})
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.load(resp)
