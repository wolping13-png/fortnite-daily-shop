from __future__ import annotations

import unittest

from everyday_one_wendell import best_video_variant, choose_candidate, normalize_candidates


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


if __name__ == "__main__":
    unittest.main()
