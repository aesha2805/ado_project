import logging

import azure.functions as func

from handle_commit import handle_request

app = func.FunctionApp()


@app.route(route="gitpush", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def gitpush(req: func.HttpRequest) -> func.HttpResponse:
    raw_text = req.get_body().decode("utf-8", errors="replace")
    try:
        notice = handle_request(raw_text)
    except Exception as error:
        logging.exception("Could not handle the push")
        return func.HttpResponse("Could not handle the push: {0}".format(error), status_code=400)
    logging.warning("RESULT\n%s", notice.strip())
    return func.HttpResponse(notice, status_code=200, mimetype="text/plain")
