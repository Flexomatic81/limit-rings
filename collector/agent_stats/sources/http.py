"""HTTP-Abruf für authentifizierte Anfragen: JSON holen, Weiterleitungen grundsätzlich ablehnen."""

import json
import urllib.error
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib behält Authorization bei Weiterleitungen, auch zu fremden Hosts – daher gar keine."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Weiterleitung abgelehnt", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def get_json(url: str, headers: dict, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "agent-stats/0.1",
                                               **headers})
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.load(resp)
