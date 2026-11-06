import json
import os
import xml.etree.ElementTree as ET

from ado_api import ado_request

SKIP_FOLDERS = ("pipeline", "function", "template")


def project_from_path(path):
    cleaned = path.replace("\\", "/").lstrip("/")
    if "/" not in cleaned:
        return ""
    return cleaned.split("/")[0]


def parse_xml(text):
    root = ET.fromstring(text)
    files = []
    for node in root.iter():
        if node.tag.endswith("File") and node.text:
            files.append(node.text.strip())

    def text_of(tag):
        for node in root.iter():
            if node.tag.endswith(tag) and node.text:
                return node.text.strip()
        return ""

    return {
        "branch": text_of("Branch") or "unknown-branch",
        "person": text_of("Person") or "unknown person",
        "email": text_of("Email"),
        "commit_message": text_of("CommitMessage") or "(no message)",
        "files": files,
        "event_type": "soap",
    }


def parse_json(payload):
    resource = payload.get("resource") or {}
    commits = resource.get("commits") or []
    first_commit = commits[0] if commits else {}
    author = first_commit.get("author") or {}
    pushed_by = resource.get("pushedBy") or {}
    ref_updates = resource.get("refUpdates") or []
    branch = ref_updates[0].get("name") if ref_updates else ""
    repository = resource.get("repository") or {}
    project = repository.get("project") or {}
    files = []
    for change in resource.get("changes") or []:
        item = change.get("item") or {}
        path = item.get("path") or ""
        if path and not item.get("isFolder"):
            files.append(path)
    return {
        "branch": branch or "unknown-branch",
        "person": pushed_by.get("displayName") or author.get("name") or "unknown person",
        "email": pushed_by.get("uniqueName") or author.get("email") or "",
        "commit_message": first_commit.get("comment") or (payload.get("message") or {}).get("text") or "(no message)",
        "files": files,
        "event_type": payload.get("eventType") or "json",
        "commit_id": first_commit.get("commitId") or "",
        "repository_url": repository.get("url") or "",
    }


def load_event(raw_text):
    stripped = raw_text.lstrip()
    if stripped.startswith("<"):
        return parse_xml(stripped)
    return parse_json(json.loads(stripped))


def fetch_changed_paths(event):
    if not event.get("repository_url") or not event.get("commit_id"):
        return []
    url = "{0}/commits/{1}/changes?api-version=7.1".format(event["repository_url"], event["commit_id"])
    status, payload = ado_request(url)
    if status != 200 or not isinstance(payload, dict):
        return []
    paths = []
    for change in payload.get("changes") or []:
        item = change.get("item") or {}
        path = item.get("path") or ""
        if path and not item.get("isFolder"):
            paths.append(path)
    return paths


def repo_targets(event):
    targets = []
    for path in event.get("files") or []:
        parts = path.replace("\\", "/").strip("/").split("/")
        if len(parts) < 2:
            continue
        project, repo = parts[0], parts[1]
        if project in SKIP_FOLDERS:
            continue
        pair = (project, repo)
        if pair not in targets:
            targets.append(pair)
    return targets


def build_notice(event):
    files = event.get("files") or []
    projects = []
    for path in files:
        name = project_from_path(path)
        if name and name not in projects and name not in SKIP_FOLDERS:
            projects.append(name)
    branch = event.get("branch", "unknown-branch").replace("refs/heads/", "")
    file_lines = "\n".join("- {0}".format(path) for path in files) if files else "- (no files)"
    project_line = ", ".join(projects) if projects else "(no project folder found)"
    org_url = os.environ.get("ADO_ORG", "").rstrip("/")
    return (
        "A request arrived from a git push.\n"
        "Org: {0}\n"
        "Event type: {1}\n"
        "Person: {2} {3}\n"
        "Branch: {4}\n"
        "Commit: {5}\n"
        "Process only these project folders: {6}\n"
        "Files:\n{7}\n"
    ).format(
        org_url,
        event.get("event_type"),
        event.get("person"),
        event.get("email"),
        branch,
        event.get("commit_message"),
        project_line,
        file_lines,
    )
