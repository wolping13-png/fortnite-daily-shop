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
    ignored_keys = {
        "displayAssets",
        "newDisplayAsset",
        "layout",
        "section",
        "bundle",
        "categories",
        "meta",
        "banner",
    }
    for key, value in entry.items():
        if key in ignored_keys:
            continue
        if not isinstance(value, list):
            continue

        for candidate in value:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("name") and (
                candidate.get("type")
                or candidate.get("images")
                or candidate.get("rarity")
                or candidate.get("series")
            ):
                items.append(candidate)

    return items


def pick_image_from_images(images: dict[str, Any] | None) -> str:
    urls = image_urls_from_images(images)
    return urls[0] if urls else ""


def image_urls_from_images(
    images: dict[str, Any] | None,
    preferred_keys: tuple[str, ...] | None = None,
) -> list[str]:
    if not isinstance(images, dict):
        return []

    if preferred_keys is None:
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


def collect_urls_recursive(value: Any) -> list[str]:
    urls: list[str] = []

    def add(url: str) -> None:
        if url.startswith("http") and url not in urls:
            urls.append(url)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if isinstance(child, str):
                    lower_key = str(key).lower()
                    lower_value = child.lower()
                    looks_like_image_key = any(
                        token in lower_key
                        for token in ("image", "icon", "background", "render", "texture", "url")
                    )
                    looks_like_image_url = any(
                        lower_value.split("?", 1)[0].endswith(ext)
                        for ext in (".png", ".jpg", ".jpeg", ".webp")
                    )
                    if looks_like_image_key or looks_like_image_url:
                        add(child)
                else:
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return urls


def pick_offer_image(entry: dict[str, Any], primary_item: dict[str, Any] | None) -> str:
    images = collect_offer_images(entry, primary_item)
    return images[0] if images else ""


def collect_tile_images(entry: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    tile_keys = ("OfferImage", "FullBackground", "Background")

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
                    add_many(image_urls_from_images(material.get("images"), tile_keys))
        add_many(collect_urls_recursive(new_display_asset))

    display_assets = entry.get("displayAssets")
    if isinstance(display_assets, list):
        for asset in display_assets:
            if isinstance(asset, dict):
                add_many(image_urls_from_images(asset.get("images"), tile_keys))
                add_many(collect_urls_recursive(asset))

    return urls


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
        add_many(collect_urls_recursive(new_display_asset))

    display_assets = entry.get("displayAssets")
    if isinstance(display_assets, list):
        for asset in display_assets:
            if isinstance(asset, dict):
                add_many(image_urls_from_images(asset.get("images")))
                add_many(collect_urls_recursive(asset))

    if isinstance(primary_item, dict):
        add_many(image_urls_from_images(primary_item.get("images")))

    bundle = entry.get("bundle")
    if isinstance(bundle, dict):
        add_many(image_urls_from_images(bundle.get("images")))

    return urls


def pick_tile_size(entry: dict[str, Any], layout: dict[str, Any]) -> str:
    return first_text(
        entry.get("tileSize"),
        entry.get("tile_size"),
        deep_get(entry, "newDisplayAsset", "tileSize"),
        deep_get(layout, "tileSize"),
        default="",
    )


def pick_sort_priority(entry: dict[str, Any], layout: dict[str, Any]) -> int:
    return first_number(
        entry.get("sortPriority"),
        entry.get("sort_priority"),
        deep_get(layout, "sortPriority"),
        deep_get(layout, "rank"),
        deep_get(layout, "index"),
        default=0,
    )


def pick_section_rank(entry: dict[str, Any], layout: dict[str, Any], index: int) -> int:
    section = entry.get("section") if isinstance(entry.get("section"), dict) else {}
    return first_number(
        deep_get(layout, "rank"),
        deep_get(layout, "index"),
        deep_get(layout, "sortPriority"),
        deep_get(section, "rank"),
        deep_get(section, "index"),
        entry.get("sectionIndex"),
        default=index,
    )


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


def pick_type(primary_item: dict[str, Any] | None) -> str:
    if not isinstance(primary_item, dict):
        return ""
    return first_text(
        deep_get(primary_item, "type", "displayValue"),
        deep_get(primary_item, "type", "value"),
        deep_get(primary_item, "type", "backendValue"),
    )


def pick_series(primary_item: dict[str, Any] | None, bundle: dict[str, Any] | None) -> str:
    for source in (primary_item, bundle):
        if isinstance(source, dict):
            value = first_text(
                deep_get(source, "series", "displayValue"),
                deep_get(source, "series", "value"),
            )
            if value:
                return value
    return ""


def pick_set_name(primary_item: dict[str, Any] | None, bundle: dict[str, Any] | None) -> str:
    for source in (primary_item, bundle):
        if isinstance(source, dict):
            value = first_text(
                deep_get(source, "set", "text"),
                deep_get(source, "set", "value"),
                deep_get(source, "set", "name"),
            )
            if value:
                return value
    return ""


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


def normalize_entry(entry: dict[str, Any], index: int) -> dict[str, Any]:
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
    section = entry.get("section") if isinstance(entry.get("section"), dict) else {}
    tile_images = collect_tile_images(entry)
    images = collect_offer_images(entry, primary_item)
    section_name = pick_section(entry, layout)

    return {
        "id": first_text(entry.get("offerId"), deep_get(primary_item, "id"), default=primary_name),
        "name": primary_name,
        "rarity": pick_rarity(primary_item, bundle),
        "series": pick_series(primary_item, bundle),
        "set": pick_set_name(primary_item, bundle),
        "type": pick_type(primary_item),
        "price": first_number(entry.get("finalPrice"), entry.get("regularPrice")),
        "image": (tile_images or images)[0] if (tile_images or images) else "",
        "tileImage": tile_images[0] if tile_images else "",
        "images": images,
        "section": section_name,
        "sectionId": first_text(
            deep_get(section, "id"),
            deep_get(layout, "id"),
            deep_get(layout, "layoutId"),
            entry.get("sectionId"),
            default=section_name,
        ),
        "sectionRank": pick_section_rank(entry, layout, index),
        "layoutId": first_text(deep_get(layout, "id"), deep_get(layout, "layoutId"), default=""),
        "layoutName": first_text(deep_get(layout, "name"), deep_get(layout, "displayName"), default=section_name),
        "tileSize": pick_tile_size(entry, layout),
        "sortPriority": pick_sort_priority(entry, layout),
        "entryIndex": index,
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

    items = [normalize_entry(entry, index) for index, entry in enumerate(entries) if isinstance(entry, dict)]
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
