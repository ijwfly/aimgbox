import asyncio
import base64
import mimetypes
from uuid import UUID

import httpx
import structlog

from aimg.providers.base import ProviderAdapter, ProviderError, ProviderResult

logger = structlog.get_logger()

_DEFAULT_BASE_URL = "https://api.replicate.com/v1"
_POLL_INTERVAL = 2
_MAX_POLLS = 120


class ReplicateAdapter(ProviderAdapter):
    def __init__(self, provider_id: UUID, config: dict | None = None) -> None:
        super().__init__(provider_id, config)
        self._api_key: str = self.config.get("api_key", "")
        self._model: str = self.config.get("model", "")
        self._version: str = self.config.get("version", "")
        self._base_url: str = self.config.get("base_url", _DEFAULT_BASE_URL)

    async def execute(
        self,
        input_data: bytes | None = None,
        params: dict | None = None,
    ) -> ProviderResult:
        prediction_input = dict(params) if params else {}

        if input_data:
            mime = mimetypes.guess_type("file.png")[0] or "image/png"
            b64 = base64.b64encode(input_data).decode()
            prediction_input["image"] = f"data:{mime};base64,{b64}"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {"version": self._version, "input": prediction_input}

        async with httpx.AsyncClient(timeout=30) as client:
            # Create prediction
            try:
                resp = await client.post(
                    f"{self._base_url}/predictions", headers=headers, json=body
                )
            except httpx.HTTPError as e:
                raise ProviderError("HTTP_ERROR", f"Replicate request failed: {e}")

            if resp.status_code not in (200, 201):
                raise ProviderError(
                    "API_ERROR",
                    f"Replicate create failed: {resp.status_code} {resp.text[:200]}",
                )

            data = resp.json()
            prediction_id = data["id"]

            # Poll for completion
            for _ in range(_MAX_POLLS):
                await asyncio.sleep(_POLL_INTERVAL)

                try:
                    poll_resp = await client.get(
                        f"{self._base_url}/predictions/{prediction_id}",
                        headers=headers,
                    )
                except httpx.HTTPError as e:
                    raise ProviderError("HTTP_ERROR", f"Replicate poll failed: {e}")

                poll_data = poll_resp.json()
                status = poll_data.get("status")

                if status == "succeeded":
                    output = poll_data.get("output")
                    if not output:
                        raise ProviderError("NO_OUTPUT", "Prediction succeeded but no output")

                    # Output can be a URL string or list of URLs
                    output_url = output[0] if isinstance(output, list) else output
                    try:
                        dl_resp = await client.get(output_url)
                        dl_resp.raise_for_status()
                    except httpx.HTTPError as e:
                        raise ProviderError("DOWNLOAD_ERROR", f"Failed to download output: {e}")

                    return ProviderResult(
                        output_data=dl_resp.content,
                        provider_job_id=prediction_id,
                    )

                if status in ("failed", "canceled"):
                    error_msg = poll_data.get("error", "Unknown error")
                    raise ProviderError(
                        "PREDICTION_FAILED",
                        f"Prediction {status}: {error_msg}",
                    )

            raise ProviderError("TIMEOUT", "Prediction timed out after polling")
