from __future__ import annotations

import unittest
from datetime import timezone
from unittest.mock import Mock

import requests
import zoneinfo

try:
    from qq_gemini_bot import (
        model_failure_reply,
        model_request_status_code,
        request_completion_with_history_fallback,
    )
except zoneinfo.ZoneInfoNotFoundError:
    original_zone_info = zoneinfo.ZoneInfo
    zoneinfo.ZoneInfo = lambda _key: timezone.utc  # type: ignore[assignment]
    try:
        from qq_gemini_bot import (
            model_failure_reply,
            model_request_status_code,
            request_completion_with_history_fallback,
        )
    finally:
        zoneinfo.ZoneInfo = original_zone_info


class ModelRequestFallbackTests(unittest.TestCase):
    @staticmethod
    def rate_limit_error() -> requests.HTTPError:
        response = Mock(status_code=429)
        response.json.return_value = {"error": {"message": "Provider rate limit exceeded"}}
        return requests.HTTPError("429 Client Error", response=response)

    def test_429_retries_without_old_history(self) -> None:
        error = self.rate_limit_error()
        request = Mock(side_effect=[error, {"choices": [{"message": {"content": "好了"}}]}])
        messages = [
            {"role": "system", "content": "persona"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "new question"},
        ]

        result = request_completion_with_history_fallback(
            {"model_history_fallback_enabled": True},
            "OpenRouter",
            request,
            messages,
            800,
        )

        self.assertEqual(result["choices"][0]["message"]["content"], "好了")
        fallback_messages = request.call_args_list[1].args[0]
        self.assertEqual(
            fallback_messages,
            [
                {"role": "system", "content": "persona"},
                {"role": "user", "content": "new question"},
            ],
        )

    def test_embedded_provider_429_is_recognized(self) -> None:
        error = RuntimeError("OpenRouter provider error 429: Provider rate limit exceeded")

        self.assertEqual(model_request_status_code(error), 429)
        self.assertIn("有点挤", model_failure_reply(error))


if __name__ == "__main__":
    unittest.main()
