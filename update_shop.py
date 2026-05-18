from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


API_URL = "https://fortnite-api.com/v2/shop"
API_LANGUAGE = "zh-Hans"
OUTPUT_PATH = Path(__file__).with_name("shop.json")
REQUEST_TIMEOUT = 30


def first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def first_number(*values: Any, default: int = 0) -> int:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return default


def deep_get(data: dict[str, Any] | None, *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def collect_offer_items(entry: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for value in entry.values():
        if not isinstance(value, list):
            continue

        for candidate in value:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("name") or candidate.get("images") or candidate.get("rarity"):
                items.append(candidate)

    return items


def pick_image_from_images(images: dict[str, Any] | None) -> str:
    urls = image_urls_from_images(images)
    return urls[0] if urls else ""


def image_urls_from_images(images: dict[str, Any] | None) -> list[str]:
    if not isinstance(images, dict):
        return []

    preferred_keys = (
        "OfferImage",
        "Background",
        "FullBackground",
        "featured",
        "icon",
        "smallIcon",
        "url",
    )
    urls: list[str] = []
    for key in preferred_keys:
        value = images.get(key)
        if isinstance(value, str) and value.startswith("http"):
            urls.append(value)

    for value in images.values():
        if isinstance(value, str) and value.startswith("http") and value not in urls:
            urls.append(value)

    return urls


def pick_offer_image(entry: dict[str, Any], primary_item: dict[str, Any] | None) -> str:
    images = collect_offer_images(entry, primary_item)
    return images[0] if images else ""


def collect_offer_images(entry: dict[str, Any], primary_item: dict[str, Any] | None) -> list[str]:
    urls: list[str] = []

    def add_many(values: list[str]) -> None:
        for value in values:
            if value and value not in urls:
                urls.append(value)

    new_display_asset = entry.get("newDisplayAsset")
    if isinstance(new_display_asset, dict):
        material_instances = new_display_asset.get("materialInstances")
        if isinstance(material_instances, list):
            for material in material_instances:
                if isinstance(material, dict):
                    add_many(image_urls_from_images(material.get("images")))

    display_assets = entry.get("displayAssets")
    if isinstance(display_assets, list):
        for asset in display_assets:
            if isinstance(asset, dict):
                add_many(image_urls_from_images(asset.get("images")))

    if isinstance(primary_item, dict):
        add_many(image_urls_from_images(primary_item.get("images")))

    bundle = entry.get("bundle")
    if isinstance(bundle, dict):
        add_many(image_urls_from_images(bundle.get("images")))

    return urls


def pick_rarity(primary_item: dict[str, Any] | None, bundle: dict[str, Any] | None) -> str:
    candidates = []
    for source in (primary_item, bundle):
        if isinstance(source, dict):
            candidates.extend(
                [
                    deep_get(source, "series", "displayValue"),
                    deep_get(source, "rarity", "displayValue"),
                    deep_get(source, "series", "value"),
                    deep_get(source, "rarity", "value"),
                ]
            )

    return first_text(*candidates, default="Unknown")


def pick_section(entry: dict[str, Any], layout: dict[str, Any]) -> str:
    section = entry.get("section") if isinstance(entry.get("section"), dict) else {}
    display_name = first_text(
        deep_get(layout, "name"),
        deep_get(layout, "displayName"),
        deep_get(section, "name"),
        deep_get(section, "displayName"),
        deep_get(layout, "category"),
        entry.get("sectionName"),
        entry.get("sectionId"),
        default="每日商店",
    )

    return display_name


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    bundle = entry.get("bundle") if isinstance(entry.get("bundle"), dict) else None
    offer_items = collect_offer_items(entry)
    primary_item = offer_items[0] if offer_items else None

    primary_name = first_text(
        deep_get(bundle, "name"),
        deep_get(primary_item, "name"),
        entry.get("devName"),
        entry.get("offerId"),
        default="Unknown Item",
    )
    if not bundle and len(offer_items) > 1:
        primary_name = f"{primary_name} + {len(offer_items) - 1}"

    layout = entry.get("layout") if isinstance(entry.get("layout"), dict) else {}
    images = collect_offer_images(entry, primary_item)

    return {
        "id": first_text(entry.get("offerId"), deep_get(primary_item, "id"), default=primary_name),
        "name": primary_name,
        "rarity": pick_rarity(primary_item, bundle),
        "price": first_number(entry.get("finalPrice"), entry.get("regularPrice")),
        "image": images[0] if images else "",
        "images": images,
        "section": pick_section(entry, layout),
    }


def fetch_shop() -> dict[str, Any]:
    response = requests.get(
        API_URL,
        params={"language": API_LANGUAGE},
        headers={"User-Agent": "fortnite-daily-shop-static-page/1.0"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, dict) or payload.get("status") != 200:
        raise RuntimeError("Fortnite API returned an unexpected response.")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Fortnite API response does not contain shop data.")

    return data


def build_shop_json(data: dict[str, Any]) -> dict[str, Any]:
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []

    items = [normalize_entry(entry) for entry in entries if isinstance(entry, dict)]
    items = [item for item in items if item["name"] and item["image"]]

    return {
        "source": API_URL,
        "language": API_LANGUAGE,
        "date": data.get("date"),
        "hash": data.get("hash"),
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vbuckIcon": data.get("vbuckIcon"),
        "items": items,
    }


def main() -> int:
    try:
        shop_json = build_shop_json(fetch_shop())
        OUTPUT_PATH.write_text(
            json.dumps(shop_json, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Failed to update shop data: {exc}", file=sys.stderr)
        return 1

    print(f"Saved {len(shop_json['items'])} shop items to {OUTPUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
