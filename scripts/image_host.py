"""
image_host.py
=============
Meta Graph API는 public URL 만 받기 때문에 PNG를 외부 호스팅에 올린 뒤
URL을 반환해야 한다. 1순위로 Cloudinary 사용.

사용법:
    from image_host import upload_image
    public_url = upload_image(Path("card_01.png"))
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def upload_image_cloudinary(local_path: Path, public_id: Optional[str] = None) -> str:
    """Cloudinary로 업로드 후 secure_url 반환."""
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )

    result = cloudinary.uploader.upload(
        str(local_path),
        public_id=public_id or local_path.stem,
        folder="cardnews",
        overwrite=True,
        resource_type="image",
    )
    return result["secure_url"]


def upload_image(local_path: Path, public_id: Optional[str] = None) -> str:
    """
    호스팅 provider 자동 감지.
    환경변수 우선순위: Cloudinary → (확장 시) S3 / Imgur.
    """
    if os.environ.get("CLOUDINARY_CLOUD_NAME"):
        return upload_image_cloudinary(local_path, public_id)

    # 확장 포인트: S3 / Imgur 등 추가 가능
    raise RuntimeError(
        "이미지 호스팅 provider 가 설정되지 않았습니다. "
        "Cloudinary 환경변수(CLOUDINARY_CLOUD_NAME, _API_KEY, _API_SECRET)를 .env에 채워주세요."
    )


if __name__ == "__main__":
    import argparse, sys

    p = argparse.ArgumentParser()
    p.add_argument("path")
    args = p.parse_args()

    url = upload_image(Path(args.path))
    print(url)
