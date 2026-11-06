import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from auth import request_headers


def ado_request(url, payload=None, method=None, timeout=60):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    if method is None:
        method = "GET" if payload is None else "POST"
    request = Request(url, data=data, method=method, headers=request_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return response.status, parsed
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = detail
        return error.code, parsed
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        return 0, str(error)
