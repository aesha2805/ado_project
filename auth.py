import base64
import os


def request_headers():
    """Sign in to Azure DevOps.

    AUTH_MODE=pat uses ADO_PAT. That is the personal-account setting.
    Finthrive will switch this function to a managed identity later.
    The repo, pipeline, and environment code calls request_headers and does not change.
    """
    mode = os.environ.get("AUTH_MODE", "pat").strip().lower() or "pat"
    if mode != "pat":
        raise RuntimeError(
            "AUTH_MODE is '{0}'. This copy signs in with ADO_PAT. "
            "The Finthrive managed-identity login is added later in auth.py.".format(mode)
        )
    pat = os.environ.get("ADO_PAT", "").strip()
    if not pat:
        raise RuntimeError("ADO_PAT is empty.")
    token = base64.b64encode(":{0}".format(pat).encode("utf-8")).decode("ascii")
    return {
        "Authorization": "Basic {0}".format(token),
        "Content-Type": "application/json",
    }
