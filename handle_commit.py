import os

from ado_setup import ensure_environments, ensure_pipeline, ensure_repo
from commit_event import fetch_changed_paths, load_event, repo_targets


def format_report(project, repo, summary):
    lines = ["{0} / {1}".format(project, repo)]
    lines.extend(summary or ["Nothing new was created."])
    return "\n".join(lines)


def handle_one(org_url, project, repo):
    repo_result = ensure_repo(org_url, project, repo)
    summary = list(repo_result.get("summary") or [])
    if not repo_result["ok"]:
        return format_report(project, repo, summary)
    try:
        pipeline = ensure_pipeline(org_url, project, repo_result["repo"])
        summary.extend(pipeline.get("summary") or [])
    except Exception as error:
        summary.append("Pipeline step failed: {0}".format(error))
    try:
        environments = ensure_environments(org_url, project)
        summary.extend(environments.get("summary") or [])
    except Exception as error:
        summary.append("Environment step failed: {0}".format(error))
    return format_report(project, repo, summary)


def handle_request(raw_text):
    org_url = os.environ.get("ADO_ORG", "").rstrip("/")
    if not org_url:
        return "Azure DevOps check skipped. Set ADO_ORG on the function."
    event = load_event(raw_text)
    if not event.get("files"):
        event["files"] = fetch_changed_paths(event)
    targets = repo_targets(event)
    if not targets:
        return "No project and repo name were found in the request."
    return "\n\n".join(handle_one(org_url, project, repo) for project, repo in targets)
