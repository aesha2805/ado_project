"""Create or leave the repo, the pipeline, and the four environments."""
import os
import time
from urllib.parse import quote

from ado_api import ado_request

EMPTY_COMMIT = "0000000000000000000000000000000000000000"
PIPELINE_PATH = "/pipeline/app.pipeline.yml"
ENVIRONMENT_NAMES = ("DEV", "QAE", "STG", "PRD")
LOCKED_NAMES = ("QAE", "STG", "PRD")
ALLOWED_BRANCH = "refs/heads/main"
TASK_CHECK = "fe1de3ee-a436-41b4-bb20-f6eb4cb879a7"
BRANCH_CONTROL = "86b05a0c-73e6-4f7d-b3cf-e38f3b39a75b"
FALLBACK_TEMPLATE = """# Copied into each repo at pipeline/app.pipeline.yml.
# This folder is the demo stand-in for Finthrive common/common-templates.

trigger:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

steps:
  - script: echo "Pipeline created from the shared demo template"
    displayName: Shared template step
"""


def wait_for_project(org_url, operation):
    if not isinstance(operation, dict) or not operation.get("id"):
        return "Project creation did not return an operation id."
    url = "{0}/_apis/operations/{1}?api-version=7.1".format(org_url, operation["id"])
    for _ in range(40):
        status, payload = ado_request(url)
        state = payload.get("status", "").lower() if isinstance(payload, dict) else ""
        if state == "succeeded":
            return ""
        if state in ("failed", "cancelled"):
            return "Project creation failed: {0}".format(payload)
        time.sleep(3)
    return "Project creation is still running."


def create_project(org_url, project):
    status, processes = ado_request("{0}/_apis/process/processes?api-version=7.1".format(org_url))
    if status != 200 or not isinstance(processes, dict) or not processes.get("value"):
        return "Could not read process templates. Azure DevOps returned {0}: {1}".format(status, processes)
    process_id = next(
        (item["id"] for item in processes["value"] if item.get("isDefault")),
        processes["value"][0]["id"],
    )
    status, created = ado_request(
        "{0}/_apis/projects?api-version=7.1".format(org_url),
        {
            "name": project,
            "description": "Created by the demo function",
            "capabilities": {
                "versioncontrol": {"sourceControlType": "Git"},
                "processTemplate": {"templateTypeId": process_id},
            },
        },
    )
    if status not in (200, 202):
        return "Project {0} was missing, but create failed. Azure DevOps returned {1}: {2}".format(project, status, created)
    return wait_for_project(org_url, created if isinstance(created, dict) else {})


def list_repos(org_url, project):
    return ado_request(
        "{0}/{1}/_apis/git/repositories?api-version=7.1".format(org_url, quote(project))
    )


def find_repo(payload, repo):
    if not isinstance(payload, dict):
        return None
    for item in payload.get("value") or []:
        if item.get("name", "").lower() == repo.lower():
            return item
    return None


def get_repo(org_url, project, repo):
    return ado_request(
        "{0}/{1}/_apis/git/repositories/{2}?api-version=7.1".format(org_url, quote(project), quote(repo))
    )


def wait_for_repo(org_url, project, repo):
    """Look up a repo that Azure DevOps already says exists, even if the list is a moment behind."""
    for _ in range(8):
        status, payload = list_repos(org_url, project)
        found = find_repo(payload, repo) if status == 200 else None
        if found is not None and found.get("id"):
            return found
        status, one = get_repo(org_url, project, repo)
        if status == 200 and isinstance(one, dict) and one.get("id"):
            return one
        time.sleep(2)
    return None


def ensure_repo(org_url, project, repo):
    """Create the project and repo when they are missing. Leave an existing repo alone."""
    status, payload = list_repos(org_url, project)
    created_project = False
    if status == 404:
        failure = create_project(org_url, project)
        if failure:
            return {"ok": False, "message": failure, "repo": None, "summary": [failure], "detail": []}
        created_project = True
        status, payload = list_repos(org_url, project)
    if status == 401:
        return {"ok": False, "message": "Azure DevOps rejected the token. Check ADO_PAT.", "repo": None, "summary": ["Azure DevOps rejected the token. Check ADO_PAT."], "detail": []}
    if status != 200:
        message = "Could not list repos in project {0}. Azure DevOps returned {1}: {2}".format(project, status, payload)
        return {
            "ok": False,
            "message": message,
            "repo": None,
            "summary": ["Could not list repos in project {0}.".format(project)],
            "detail": [message],
        }
    found = find_repo(payload, repo)
    if found is not None:
        if created_project:
            message = "Project {0} was missing. Created the project. Repo {1} was already there. Ignored.".format(project, repo)
            summary = ["Project {0} was created.".format(project)]
            detail = ["Repo {0} was already there.".format(repo)]
        else:
            message = "Repo {0} already exists in project {1}. Ignored.".format(repo, project)
            summary = []
            detail = [message]
        return {"ok": True, "message": message, "repo": found, "summary": summary, "detail": detail}
    status, created = ado_request(
        "{0}/{1}/_apis/git/repositories?api-version=7.1".format(org_url, quote(project)),
        {"name": repo},
    )
    if status == 409:
        found = wait_for_repo(org_url, project, repo)
        if found is not None:
            message = "Repo {0} already exists in project {1}. Ignored.".format(repo, project)
            return {"ok": True, "message": message, "repo": found, "summary": [], "detail": [message]}
    if status not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
        message = "Repo {0} was missing in project {1}, but create failed. Azure DevOps returned {2}: {3}".format(
            repo, project, status, created
        )
        return {
            "ok": False,
            "message": message,
            "repo": None,
            "summary": ["Repo {0} could not be created.".format(repo)],
            "detail": [message],
        }
    web = created.get("webUrl") or created.get("remoteUrl") or ""
    if created_project:
        message = "Project {0} was not in Azure DevOps. Created the project and repo {1}. {2}".format(project, repo, web).strip()
        summary = ["Project {0} was created.".format(project), "Repo {0} was created.".format(repo)]
    else:
        message = "Repo {0} was not in project {1}. Created it. {2}".format(repo, project, web).strip()
        summary = ["Repo {0} was created.".format(repo)]
    return {"ok": True, "message": message, "repo": created, "summary": summary, "detail": [message]}


def template_text():
    configured = os.environ.get("TEMPLATE_PATH", "").strip()
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        configured,
        os.path.join(here, "template", "app.pipeline.yml"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
    return FALLBACK_TEMPLATE


def pipeline_for_repo(org_url, project, repo_id):
    status, payload = ado_request(
        "{0}/{1}/_apis/build/definitions?repositoryId={2}&repositoryType=TfsGit&api-version=7.1".format(
            org_url, quote(project), repo_id
        )
    )
    if status != 200 or not isinstance(payload, dict):
        return status, None
    values = payload.get("value") or []
    return status, values[0] if values else None


def file_on_main(org_url, project, repo_id):
    status, payload = ado_request(
        "{0}/{1}/_apis/git/repositories/{2}/items?path={3}&versionDescriptor.version=main&versionDescriptor.versionType=branch&api-version=7.1".format(
            org_url, quote(project), repo_id, quote(PIPELINE_PATH)
        )
    )
    return status == 200, payload


def main_commit(org_url, project, repo_id):
    status, payload = ado_request(
        "{0}/{1}/_apis/git/repositories/{2}/refs?filter=heads/main&api-version=7.1".format(
            org_url, quote(project), repo_id
        )
    )
    if status == 200 and isinstance(payload, dict) and payload.get("value"):
        return payload["value"][0]["objectId"]
    return EMPTY_COMMIT


def copy_template(org_url, project, repo_id):
    present, _payload = file_on_main(org_url, project, repo_id)
    if present:
        return "Template file {0} is already in the repo.".format(PIPELINE_PATH)
    status, pushed = ado_request(
        "{0}/{1}/_apis/git/repositories/{2}/pushes?api-version=7.1".format(org_url, quote(project), repo_id),
        {
            "refUpdates": [{"name": "refs/heads/main", "oldObjectId": main_commit(org_url, project, repo_id)}],
            "commits": [
                {
                    "comment": "Add pipeline template",
                    "changes": [
                        {
                            "changeType": "add",
                            "item": {"path": PIPELINE_PATH},
                            "newContent": {"content": template_text(), "contentType": "rawtext"},
                        }
                    ],
                }
            ],
        },
    )
    if status not in (200, 201):
        return "Could not copy the template into the repo. Azure DevOps returned {0}: {1}".format(status, pushed)
    ado_request(
        "{0}/{1}/_apis/git/repositories/{2}?api-version=7.1".format(org_url, quote(project), repo_id),
        {"defaultBranch": "refs/heads/main"},
        method="PATCH",
    )
    return "Copied template/app.pipeline.yml to {0}.".format(PIPELINE_PATH)


def ensure_pipeline(org_url, project, repo):
    repo_id = repo.get("id")
    repo_name = repo.get("name")
    if not repo_id:
        message = "Pipeline was not checked because the repo id is missing."
        return {"message": message, "summary": [message], "detail": []}
    status, existing = pipeline_for_repo(org_url, project, repo_id)
    if status != 200:
        message = "Could not list pipelines in project {0}. Azure DevOps returned {1}.".format(project, status)
        return {"message": message, "summary": ["Could not list pipelines in project {0}.".format(project)], "detail": [message]}
    if existing is not None:
        message = "Pipeline for repo {0} already exists. Ignored.".format(repo_name)
        return {"message": message, "summary": [], "detail": [message]}
    copied = copy_template(org_url, project, repo_id)
    if copied.startswith("Could not copy"):
        return {"message": copied, "summary": ["The pipeline template could not be copied."], "detail": [copied]}
    status, created = ado_request(
        "{0}/{1}/_apis/pipelines?api-version=7.1".format(org_url, quote(project)),
        {
            "folder": "\\",
            "name": repo_name,
            "configuration": {
                "type": "yaml",
                "path": PIPELINE_PATH,
                "repository": {
                    "id": repo_id,
                    "name": repo_name,
                    "type": "azureReposGit",
                },
            },
        },
    )
    if status not in (200, 201) or not isinstance(created, dict):
        message = "{0} Pipeline create failed. Azure DevOps returned {1}: {2}".format(copied, status, created)
        return {"message": message, "summary": ["Pipeline {0} could not be created.".format(repo_name)], "detail": [message]}
    pipeline_name = created.get("name") or repo_name
    message = "{0} Created pipeline {1} in the open list.".format(copied, pipeline_name)
    return {
        "message": message,
        "summary": ["Pipeline {0} was created.".format(pipeline_name)],
        "detail": [copied, "Created pipeline {0} in the open list.".format(pipeline_name)],
    }


def environment_url(org_url, project):
    return "{0}/{1}/_apis/distributedtask/environments?api-version=7.1".format(org_url, quote(project))


def list_environments(org_url, project):
    status, payload = ado_request(environment_url(org_url, project))
    if status != 200 or not isinstance(payload, dict):
        return status, []
    return status, payload.get("value") or []


def create_environment(org_url, project, name):
    return ado_request(environment_url(org_url, project), {"name": name, "description": "Created by the demo function"})


def checks_url(org_url, project, environment_id):
    return (
        "{0}/{1}/_apis/pipelines/checks/configurations"
        "?resourceType=environment&resourceId={2}&%24expand=settings&api-version=7.1-preview.1"
    ).format(org_url, quote(project), environment_id)


def branch_checks(org_url, project, environment_id):
    status, payload = ado_request(checks_url(org_url, project, environment_id))
    if status != 200 or not isinstance(payload, dict):
        return status, []
    found = []
    for check in payload.get("value") or []:
        settings = check.get("settings") or {}
        definition = settings.get("definitionRef") or {}
        if (definition.get("id") or "").lower() == BRANCH_CONTROL:
            found.append(check)
    return status, found


def allowed_branches(check):
    settings = check.get("settings") or {}
    inputs = settings.get("inputs") or {}
    return (inputs.get("allowedBranches") or "").strip()


def branch_control_body(environment_id, name, branch=ALLOWED_BRANCH):
    return {
        "type": {"id": TASK_CHECK, "name": "Task Check"},
        "settings": {
            "definitionRef": {
                "id": BRANCH_CONTROL,
                "name": "evaluatebranchProtection",
                "version": "0.0.1",
            },
            "displayName": "Branch control",
            "inputs": {
                "allowedBranches": branch,
                "ensureProtectionOfBranch": "false",
                "allowUnknownStatusBranch": "false",
            },
            "retryInterval": 5,
        },
        "resource": {"type": "environment", "id": str(environment_id), "name": name},
        "timeout": 43200,
    }


def set_allowed_branch(org_url, project, environment):
    environment_id = environment.get("id")
    name = environment.get("name")
    status, checks = branch_checks(org_url, project, environment_id)
    if status != 200:
        return "{0}: could not read the branch rule. Azure DevOps returned {1}.".format(name, status)
    if len(checks) == 1 and allowed_branches(checks[0]) == ALLOWED_BRANCH:
        return "{0}: allowed branch is already {1}. Ignored.".format(name, ALLOWED_BRANCH)
    for check in checks:
        ado_request(
            "{0}/{1}/_apis/pipelines/checks/configurations/{2}?api-version=7.1-preview.1".format(
                org_url, quote(project), check.get("id")
            ),
            method="DELETE",
        )
    status, created = ado_request(
        "{0}/{1}/_apis/pipelines/checks/configurations?api-version=7.1-preview.1".format(org_url, quote(project)),
        branch_control_body(environment_id, name),
    )
    if status not in (200, 201):
        return "{0}: could not set the allowed branch. Azure DevOps returned {1}: {2}".format(name, status, created)
    if checks:
        return "{0}: allowed branch was changed. Set it back to {1}.".format(name, ALLOWED_BRANCH)
    return "{0}: set allowed branch to {1}.".format(name, ALLOWED_BRANCH)


def clear_dev_branch(org_url, project, environment):
    """DEV has no branch control. Remove one if an older run added it."""
    status, checks = branch_checks(org_url, project, environment.get("id"))
    if status != 200:
        return "DEV: could not read the branch rule. Azure DevOps returned {0}.".format(status)
    if not checks:
        return "DEV: no branch control. Ignored."
    for check in checks:
        ado_request(
            "{0}/{1}/_apis/pipelines/checks/configurations/{2}?api-version=7.1-preview.1".format(
                org_url, quote(project), check.get("id")
            ),
            method="DELETE",
        )
    return "DEV: branch control was removed."


def name_list(names):
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "{0} and {1}".format(names[0], names[1])
    return "{0}, and {1}".format(", ".join(names[:-1]), names[-1])


def ensure_environments(org_url, project):
    """Create DEV, QAE, STG, and PRD. Force main on QAE, STG, and PRD. Leave DEV unlocked."""
    summary = []
    detail = []
    status, current = list_environments(org_url, project)
    if status != 200:
        message = "Could not list environments in project {0}. Azure DevOps returned {1}.".format(project, status)
        return {"message": message, "summary": ["Could not list environments in project {0}.".format(project)], "detail": [message]}
    by_name = {item.get("name", "").upper(): item for item in current}
    created = []
    set_to_main = []
    for name in ENVIRONMENT_NAMES:
        if name not in by_name:
            status, created_env = create_environment(org_url, project, name)
            if status not in (200, 201) or not isinstance(created_env, dict):
                message = "{0}: create failed. Azure DevOps returned {1}: {2}".format(name, status, created_env)
                summary.append("{0} could not be created.".format(name))
                detail.append(message)
                continue
            by_name[name] = created_env
            created.append(name)
            detail.append("{0}: created.".format(name))
        else:
            detail.append("{0}: already exists. Ignored.".format(name))
        if name in LOCKED_NAMES:
            text = set_allowed_branch(org_url, project, by_name[name])
            detail.append(text)
            if "was changed" in text:
                summary.append("{0} allowed branch was wrong. Set it back to {1}.".format(name, ALLOWED_BRANCH))
            elif ": set allowed branch to " in text:
                set_to_main.append(name)
        else:
            text = clear_dev_branch(org_url, project, by_name[name])
            detail.append(text)
            if "was removed" in text:
                summary.append("DEV branch control was removed.")
    if created:
        label = name_list(created)
        summary.insert(0, "{0} {1} created.".format(label, "was" if len(created) == 1 else "were"))
    if set_to_main:
        label = name_list(set_to_main)
        summary.append("{0} {1} set to {2}.".format(label, "was" if len(set_to_main) == 1 else "were", ALLOWED_BRANCH))
    return {"message": "\n".join(detail), "summary": summary, "detail": detail}
