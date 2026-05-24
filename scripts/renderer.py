"""
renderer.py
===========
카드 데이터(JSON) → HTML 주입 → Playwright 캡처 → PNG 저장.

정보형 카드 구조 (cover/intro/point/tip/summary/cta).
- 1080x1080 PNG
- bottom-stack 고정 (page indicator + 사인오프)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import yaml
from playwright.async_api import async_playwright


# ----------------------------------------------------------
# 카드 타입별 메인 콘텐츠 HTML 빌더
# ----------------------------------------------------------
def _accent(text: str, accent: str | None) -> str:
    """텍스트 안 강조 단어를 <span class="accent">로 감싸기."""
    if not accent or accent not in text:
        return text
    return text.replace(accent, f'<span class="accent">{accent}</span>', 1)


def _build_main_html(card: dict) -> str:
    t = card.get("type", "")
    headline = card.get("headline", "")
    subhead = card.get("subhead", "")
    body = card.get("body", "")
    accent = card.get("accent", "")
    label = card.get("label", "")

    if t in ("cover", "intro", "summary"):
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="subhead">{subhead}</div>
        """

    if t == "point":
        return f"""
        <div class="point-num">{label}</div>
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="body">{body}</div>
        """

    if t == "tip":
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="tip-box">{body}</div>
        """

    if t == "cta":
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="subhead">{subhead}</div>
        """

    # fallback
    return f'<div class="headline">{headline}</div><div class="subhead">{subhead}</div>'


def _build_top_label_block(card: dict) -> str:
    # point 카드는 큰 숫자(point-num)로 표시하므로 상단 라벨 생략
    if card.get("type") == "point":
        return ""
    label = card.get("label", "")
    if not label:
        return ""
    return f'<div class="top-label"><span>{label}</span></div>'


def _build_corner_quote_block(card: dict) -> str:
    if card.get("type") in ("summary", "tip"):
        return '<div class="corner-quote">&ldquo;</div>'
    return ""


# ----------------------------------------------------------
# 메인 렌더링
# ----------------------------------------------------------
def render_html_for_card(
    card: dict,
    page_num: int,
    total_pages: int,
    template_str: str,
    brand: str,
    swipe_text: str,
) -> str:
    html = template_str
    replacements = {
        "{{TITLE}}": f"Card {page_num}",
        "{{CARD_TYPE}}": card.get("type", "cover"),
        "{{TOP_LABEL_BLOCK}}": _build_top_label_block(card),
        "{{CORNER_QUOTE_BLOCK}}": _build_corner_quote_block(card),
        "{{MAIN_CONTENT}}": _build_main_html(card),
        "{{PAGE_NUM}}": f"{page_num:02d}",
        "{{TOTAL_PAGES}}": f"{total_pages:02d}",
        "{{BRAND}}": brand,
        "{{SWIPE_TEXT}}": swipe_text if page_num < total_pages else "끝까지 봐주셔서 감사합니다",
    }
    for k, v in replacements.items():
        html = html.replace(k, v)
    return html


async def _render_one(page, html: str, output_path: Path, width: int, height: int):
    await page.set_viewport_size({"width": width, "height": height})
    await page.set_content(html, wait_until="networkidle")
    await page.wait_for_timeout(300)
    await page.screenshot(
        path=str(output_path),
        clip={"x": 0, "y": 0, "width": width, "height": height},
        type="png",
        omit_background=False,
    )


async def render_card_set_async(
    card_set: dict,
    output_dir: Path,
    config_path: str = "config.yaml",
) -> list[Path]:
    """카드 세트를 받아 8장 PNG 생성. 반환: 생성된 파일 경로 리스트."""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    width = cfg["design"]["width"]
    height = cfg["design"]["height"]
    template_path = cfg["paths"]["template"]
    brand = os.environ.get("BRAND_NAME") or cfg["branding"]["sign_off"]
    swipe = cfg["branding"]["swipe_cta"]

    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()

    cards = card_set["cards"]
    total = len(cards)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_paths: list[Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=cfg["render"].get("scale", 1),
        )
        page = await ctx.new_page()

        for i, card in enumerate(cards, start=1):
            html = render_html_for_card(
                card, i, total, template_str, brand, swipe
            )
            out_path = output_dir / f"card_{i:02d}.png"
            await _render_one(page, html, out_path, width, height)
            out_paths.append(out_path)

        await browser.close()

    return out_paths


def render_card_set(
    card_set: dict,
    output_dir: Path,
    config_path: str = "config.yaml",
) -> list[Path]:
    """동기 wrapper."""
    return asyncio.run(render_card_set_async(card_set, output_dir, config_path))


# ----------------------------------------------------------
# CLI
# ----------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser()
    p.add_argument("--card-json", required=True, help="content_generator.py 결과 JSON 경로")
    p.add_argument("--out-dir", required=True, help="PNG 출력 디렉터리")
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args()

    with open(args.card_json, "r", encoding="utf-8") as f:
        card_set = json.load(f)

    paths = render_card_set(card_set, Path(args.out_dir), args.config)
    for path in paths:
        print(path)
