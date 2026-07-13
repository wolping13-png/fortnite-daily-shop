from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from everyday_one_wendell import (
    best_video_variant,
    choose_candidate,
    normalize_candidates,
    resolve_author,
    x_get,
)


class EveryOneWendellTests(unittest.TestCase):
    def test_retweet_uses_original_post_and_best_video(self) -> None:
        payload = {
            "data": [
                {
                    "id": "300",
                    "author_id": "1",
                    "text": "RT",
                    "created_at": "2026-07-13T01:00:00.000Z",
                    "referenced_tweets": [{"type": "retweeted", "id": "200"}],
                }
            ],
            "includes": {
                "tweets": [
                    {
                        "id": "200",
                        "author_id": "2",
                        "text": "Original post https://t.co/media",
                        "created_at": "2026-07-12T23:00:00.000Z",
                        "attachments": {"media_keys": ["m1"]},
                    }
                ],
                "users": [
                    {"id": "1", "username": "wendellindashop", "name": "Wendell"},
                    {"id": "2", "username": "artist", "name": "Artist"},
                ],
                "media": [
                    {
                        "media_key": "m1",
                        "type": "animated_gif",
                        "preview_image_url": "https://example.com/preview.jpg",
                        "variants": [
                            {"content_type": "video/mp4", "url": "https://example.com/low.mp4", "bit_rate": 256000},
                            {"content_type": "video/mp4", "url": "https://example.com/high.mp4", "bit_rate": 832000},
                        ],
                    }
                ],
            },
        }

        posts = normalize_candidates(payload, "wendellindashop")

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["id"], "200")
        self.assertEqual(posts[0]["source_id"], "300")
        self.assertEqual(posts[0]["username"], "artist")
        self.assertTrue(posts[0]["is_retweet"])
        self.assertEqual(posts[0]["media"][0]["url"], "https://example.com/high.mp4")

    def test_best_video_variant_ignores_hls(self) -> None:
        media = {
            "variants": [
                {"content_type": "application/x-mpegURL", "url": "https://example.com/video.m3u8"},
                {"content_type": "video/mp4", "url": "https://example.com/video.mp4"},
            ]
        }
        self.assertEqual(best_video_variant(media)["url"], "https://example.com/video.mp4")

    def test_partial_delivery_is_retried_before_a_new_post(self) -> None:
        candidates = [{"id": "300"}, {"id": "200"}]
        deliveries = {"200": ["111"]}

        selected = choose_candidate(candidates, deliveries, [111, 222])

        self.assertEqual(selected["id"], "200")

    @patch("everyday_one_wendell.time.sleep")
    @patch("everyday_one_wendell.requests.get")
    def test_x_get_retries_temporary_503(self, request_get: Mock, sleep: Mock) -> None:
        unavailable = Mock(status_code=503, text="unavailable")
        success = Mock(status_code=200)
        success.json.return_value = {"data": {"id": "1"}}
        success.raise_for_status.return_value = None
        request_get.side_effect = [unavailable, success]

        result = x_get("https://api.x.com/test", "token")

        self.assertEqual(result["data"]["id"], "1")
        self.assertEqual(request_get.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch("everyday_one_wendell.x_get")
    def test_author_lookup_falls_back_to_batch_endpoint(self, request: Mock) -> None:
        request.side_effect = [
            RuntimeError("503"),
            {"data": [{"id": "42", "username": "wendellindashop", "name": "Wendell"}]},
        ]
        state: dict = {}

        author = resolve_author("token", "wendellindashop", state)

        self.assertEqual(author["id"], "42")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(state["author"]["username"], "wendellindashop")


if __name__ == "__main__":
    unittest.main()
