import asyncio
import base64
from uuid import UUID

import httpx
import structlog

from aimg.providers.base import ProviderAdapter, ProviderError, ProviderResult

logger = structlog.get_logger()

_DEFAULT_BASE_URL = "https://api.replicate.com/v1"
_POLL_INTERVAL = 2
_MAX_POLLS = 120


def _detect_mime_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


class ReplicateAdapter(ProviderAdapter):
    def __init__(self, provider_id: UUID, config: dict | None = None) -> None:
        super().__init__(provider_id, config)
        self._api_key: str = self.config.get("api_key", "")
        self._model: str = self.config.get("model", "")
        self._version: str = self.config.get("version", "")
        self._base_url: str = self.config.get("base_url", _DEFAULT_BASE_URL)
        self._input_field: str = self.config.get("input_field", "image")
        self._input_as_array: bool = self.config.get("input_as_array", False)
        self._exclude_params: list[str] = self.config.get("exclude_params", [])
        self._default_params: dict = self.config.get("default_params", {})
        self._sync_mode: bool = self.config.get("sync_mode", False)

    async def execute(
        self,
        input_data: bytes | None = None,
        params: dict | None = None,
    ) -> ProviderResult:
        # Build prediction input: defaults < handler params < exclude filter
        prediction_input = {**self._default_params}
        if params:
            prediction_input.update(params)
        for key in self._exclude_params:
            prediction_input.pop(key, None)

        if input_data:
            mime = _detect_mime_type(input_data)
            b64 = base64.b64encode(input_data).decode()
            data_uri = f"data:{mime};base64,{b64}"
            if self._input_as_array:
                prediction_input[self._input_field] = [data_uri]
            else:
                prediction_input[self._input_field] = data_uri

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Model-based endpoint vs legacy version-based endpoint
        if self._model and not self._version:
            url = f"{self._base_url}/models/{self._model}/predictions"
            body: dict = {"input": prediction_input}
        else:
            url = f"{self._base_url}/predictions"
            body = {"version": self._version, "input": prediction_input}

        if self._sync_mode:
            headers["Prefer"] = "wait"

        async with httpx.AsyncClient(timeout=300) as client:
            # Create prediction
            try:
                resp = await client.post(url, headers=headers, json=body)
            except httpx.HTTPError as e:
                raise ProviderError("HTTP_ERROR", f"Replicate request failed: {e}")

            if resp.status_code not in (200, 201):
                raise ProviderError(
                    "API_ERROR",
                    f"Replicate create failed: {resp.status_code} {resp.text[:500]}",
                )

            data = resp.json()
            prediction_id = data["id"]

            # Sync mode: check if result is already available
            if self._sync_mode and data.get("status") == "succeeded":
                return await self._extract_output(client, data, prediction_id)

            # Poll for completion
            fallback_url = f"{self._base_url}/predictions/{prediction_id}"
            poll_url = data.get("urls", {}).get("get", fallback_url)
            for _ in range(_MAX_POLLS):
                await asyncio.sleep(_POLL_INTERVAL)

                try:
                    poll_resp = await client.get(poll_url, headers=headers)
                except httpx.HTTPError as e:
                    raise ProviderError("HTTP_ERROR", f"Replicate poll failed: {e}")

                poll_data = poll_resp.json()
                status = poll_data.get("status")

                if status == "succeeded":
                    return await self._extract_output(client, poll_data, prediction_id)

                if status in ("failed", "canceled"):
                    error_msg = poll_data.get("error", "Unknown error")
                    raise ProviderError(
                        "PREDICTION_FAILED",
                        f"Prediction {status}: {error_msg}",
                    )

            raise ProviderError("TIMEOUT", "Prediction timed out after polling")

    async def _extract_output(
        self,
        client: httpx.AsyncClient,
        data: dict,
        prediction_id: str,
    ) -> ProviderResult:
        output = data.get("output")
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
