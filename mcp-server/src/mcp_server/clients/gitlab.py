"""Thin python-gitlab wrapper -- read-only. The MCP Server queries pipeline
status here (Platform-v2-Reference-Architecture.md §7.7); it never triggers
pipelines itself -- that is a native Nautobot webhook (see the webhook
created against tenancy.tenant in Nautobot, not this client).
"""
from __future__ import annotations

import gitlab

from mcp_server.errors import GitLabError


class GitLabClient:
    def __init__(self, url: str, token: str, project_id: str) -> None:
        self._url = url
        self._token = token
        self._project_id = project_id
        self._gl: gitlab.Gitlab | None = None

    @property
    def _client(self) -> gitlab.Gitlab:
        if self._gl is None:
            self._gl = gitlab.Gitlab(self._url, private_token=self._token or None, keep_base_url=True)
        return self._gl

    def latest_pipeline(self) -> dict | None:
        """Most recent pipeline on the default branch -- used by show_status
        to report the pipeline a create_tenant call most likely triggered.
        """
        try:
            project = self._client.projects.get(self._project_id)
            pipelines = project.pipelines.list(per_page=1, order_by="id", sort="desc", get_all=False)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"GitLab unreachable or auth failed: {exc}") from exc
        if not pipelines:
            return None
        p = pipelines[0]
        return {
            "id": p.id,
            "status": p.status,
            "web_url": p.web_url,
            "ref": p.ref,
            "sha": p.sha,
            "source": getattr(p, "source", None),
        }

    def pipeline(self, pipeline_id: int) -> dict | None:
        try:
            project = self._client.projects.get(self._project_id)
            p = project.pipelines.get(pipeline_id)
        except gitlab.exceptions.GitlabGetError:
            return None
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"GitLab unreachable or auth failed: {exc}") from exc
        return {
            "id": p.id,
            "status": p.status,
            "web_url": p.web_url,
            "ref": p.ref,
            "sha": p.sha,
        }
