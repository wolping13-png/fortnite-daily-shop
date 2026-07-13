from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from everyday_one_wendell import (
    best_video_variant,
    choose_candidate,
    choose_private_candidate,
    fetch_public_rss_posts,
    normalize_candidates,
    resolve_author,
    split_video_message_batches,
    x_get,
    x_get_with_available_auth,
)


class EveryDayOneWendellTests(unittest.TestCase):
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

    def test_private_retweet_preview_selects_latest_retweet(self) -> None:
        candidates = [
            {"id": "300", "is_retweet": False},
            {"id": "200", "is_retweet": True},
            {"id": "100", "is_retweet": True},
        ]

        selected = choose_private_candidate(candidates, retweet_only=True)

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

    @patch("everyday_one_wendell.x_get")
    @patch("everyday_one_wendell.x_user_get")
    def test_oauth_token_is_preferred_when_x_timeline_is_configured(
        self,
        user_get: Mock,
        bearer_get: Mock,
    ) -> None:
        user_get.return_value = {"data": {"id": "42"}}
        config = {"x_user_access_token": "oauth-token"}

        result = x_get_with_available_auth(
            "https://api.x.com/test",
            "bearer-token",
            config=config,
        )

        self.assertEqual(result["data"]["id"], "42")
        user_get.assert_called_once()
        bearer_get.assert_not_called()

    @patch("everyday_one_wendell.x_get_with_available_auth")
    def test_default_author_id_skips_username_lookup(self, request: Mock) -> None:
        state: dict = {}

        author = resolve_author(
            "bearer-token",
            "wendellindashop",
            state,
            config={"x_user_access_token": "oauth-token"},
        )

        self.assertEqual(author["id"], "1837315425178136576")
        self.assertEqual(author["name"], "Days without Wendell in the shop")
        request.assert_not_called()

    @patch("everyday_one_wendell.requests.get")
    def test_public_rss_includes_original_retweet_and_video(self, request_get: Mock) -> None:
        response = Mock()
        response.content = b"""<?xml version='1.0' encoding='UTF-8'?>
        <rss xmlns:dc='http://purl.org/dc/elements/1.1/'><channel><item>
          <title>RT by @wendellindashop: Original text</title>
          <dc:creator>@artist</dc:creator>
          <pubDate>Mon, 13 Jul 2026 00:43:27 GMT</pubDate>
          <guid>2076467506898755746</guid>
          <link>https://nitter.net/artist/status/2076467506898755746#m</link>
          <description><![CDATA[<p>Original text</p><video><source src='https://nitter.net/pic/video.mp4' type='video/mp4'></video>]]></description>
        </item></channel></rss>"""
        response.raise_for_status.return_value = None
        request_get.return_value = response

        posts = fetch_public_rss_posts("wendellindashop", {}, limit=5)

        self.assertEqual(posts[0]["username"], "artist")
        self.assertTrue(posts[0]["is_retweet"])
        self.assertEqual(posts[0]["media"][0]["type"], "video")
        self.assertEqual(posts[0]["url"], "https://x.com/artist/status/2076467506898755746")

    def test_video_is_sent_after_text_in_a_separate_message(self) -> None:
        message = [
            {"type": "text", "data": {"text": "post text"}},
            {"type": "video", "data": {"file": "file:///video.mp4"}},
        ]

        batches = split_video_message_batches(message)

        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0][0]["type"], "text")
        self.assertEqual(batches[1][0]["type"], "video")

    def test_looping_rss_video_is_detected_as_animated_gif(self) -> None:
        from everyday_one_wendell import RssDescriptionParser

        parser = RssDescriptionParser("https://nitter.net/")
        parser.feed(
            "<video autoplay muted loop><source src='/pic/tweet_video/example.mp4' "
            "type='video/mp4'></video>"
        )

        self.assertEqual(parser.parsed_media()[0]["type"], "animated_gif")


if __name__ == "__main__":
    unittest.main()
