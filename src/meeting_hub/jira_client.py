import httpx

from meeting_hub.models import ActionItem, JiraSyncResult


class JiraServiceError(RuntimeError):
    """The Jira task service is unreachable or rejected the request."""


class JiraServiceClient:
    """Talks to the Jira task service (poc_jira) over HTTP."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"X-API-Key": api_key} if api_key else {}
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport
        )

    async def sync_action_items(
        self,
        items: list[ActionItem],
        *,
        meeting_id: str,
        meeting_title: str,
        dry_run: bool = False,
    ) -> JiraSyncResult:
        payload = {
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "dry_run": dry_run,
            "action_items": [item.model_dump() for item in items],
        }
        try:
            response = await self._http.post("/tasks", json=payload)
        except httpx.HTTPError as exc:
            raise JiraServiceError(f"Could not reach the Jira service: {exc}") from exc
        if response.is_error:
            raise JiraServiceError(
                f"Jira service returned {response.status_code}: {_detail(response)}"
            )
        return JiraSyncResult.model_validate(response.json())

    async def close(self) -> None:
        await self._http.aclose()


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text[:300]
