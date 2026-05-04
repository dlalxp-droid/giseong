"""
ig_uploader.py
==============
Meta Graph API v21.0 캐러셀 게시 흐름 구현.

흐름 (Meta 공식 문서 기준):
  1. 각 PNG 별로 /media 호출 (is_carousel_item=true) → child container_id
  2. /media (media_type=CAROUSEL, children=ids) → 부모 container_id
  3. /media_publish (creation_id=부모) → 게시 완료

Reels 와 피드 분리: 본 코드는 캐러셀(=피드 그리드 노출)만 다룬다.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterable

import requests


GRAPH_BASE = "https://graph.facebook.com"


# ----------------------------------------------------------
# 저수준 호출
# ----------------------------------------------------------
def _create_child_container(
    ig_user_id: str,
    access_token: str,
    image_url: str,
    api_version: str = "v21.0",
) -> str:
    url = f"{GRAPH_BASE}/{api_version}/{ig_user_id}/media"
    payload = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": access_token,
    }
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _create_carousel_container(
    ig_user_id: str,
    access_token: str,
    children_ids: list[str],
    caption: str,
    api_version: str = "v21.0",
) -> str:
    url = f"{GRAPH_BASE}/{api_version}/{ig_user_id}/media"
    payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": access_token,
    }
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _publish_container(
    ig_user_id: str,
    access_token: str,
    creation_id: str,
    api_version: str = "v21.0",
) -> str:
    url = f"{GRAPH_BASE}/{api_version}/{ig_user_id}/media_publish"
    payload = {"creation_id": creation_id, "access_token": access_token}
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _wait_until_ready(
    container_id: str,
    access_token: str,
    api_version: str = "v21.0",
    timeout_sec: int = 120,
    poll_sec: int = 3,
) -> None:
    """미디어 컨테이너 status_code가 FINISHED 가 될 때까지 대기.
    (Meta는 비동기 처리. 즉시 publish하면 IN_PROGRESS 에러 발생)"""
    url = f"{GRAPH_BASE}/{api_version}/{container_id}"
    deadline = time.time() + timeout_sec
    last_status = None
    while time.time() < deadline:
        r = requests.get(
            url,
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        r.raise_for_status()
        status = r.json().get("status_code")
        last_status = status
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Container {container_id} failed processing")
        time.sleep(poll_sec)
    raise TimeoutError(
        f"Container {container_id} not ready in {timeout_sec}s (last={last_status})"
    )


# ----------------------------------------------------------
# 고수준
# ----------------------------------------------------------
def publish_carousel(
    image_urls: Iterable[str],
    caption: str,
    ig_user_id: str | None = None,
    access_token: str | None = None,
    api_version: str = "v21.0",
) -> str:
    """
    이미지 URL 리스트와 캡션을 받아 캐러셀 게시. 게시된 미디어 ID 반환.
    """
    ig_user_id = ig_user_id or os.environ["IG_USER_ID"]
    access_token = access_token or os.environ["META_ACCESS_TOKEN"]

    image_urls = list(image_urls)
    if not 2 <= len(image_urls) <= 10:
        raise ValueError(
            f"Carousel must have 2~10 items, got {len(image_urls)}"
        )

    # 1) 자식 컨테이너 N개 생성
    child_ids = []
    for url in image_urls:
        cid = _create_child_container(ig_user_id, access_token, url, api_version)
        child_ids.append(cid)
        # 비동기 처리 대기
        _wait_until_ready(cid, access_token, api_version, timeout_sec=60)

    # 2) 캐러셀 부모 컨테이너
    parent_id = _create_carousel_container(
        ig_user_id, access_token, child_ids, caption, api_version
    )
    _wait_until_ready(parent_id, access_token, api_version, timeout_sec=120)

    # 3) 게시
    media_id = _publish_container(ig_user_id, access_token, parent_id, api_version)
    return media_id


# ----------------------------------------------------------
# CLI (수동 테스트용)
# ----------------------------------------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--urls", required=True, help="쉼표 구분 이미지 URL 목록")
    p.add_argument("--caption-file", required=True, help="캡션 텍스트 파일")
    args = p.parse_args()

    urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    caption = Path(args.caption_file).read_text(encoding="utf-8")

    media_id = publish_carousel(urls, caption)
    print(f"Published media id: {media_id}")
