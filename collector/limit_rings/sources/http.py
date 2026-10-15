"""HTTP fetching for authenticated requests: get JSON, always refuse redirects."""

import json
import urllib.error
import urllib.request
from email.message import Message
from typing import IO, Any, NoReturn

from ..version import VERSION


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib keeps Authorization on redirects, even to foreign hosts – so allow none at all."""

    def redirect_request(
        self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: Message, newurl: str
    ) -> NoReturn:
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def get_json(url: str, headers: dict[str, str], timeout: float = 10.0) -> Any:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": f"limit-rings/{VERSION}", **headers}
    )
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.load(resp)
