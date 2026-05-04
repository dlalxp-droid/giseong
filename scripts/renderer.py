"""
renderer.py
===========
카드 데이터(JSON) → HTML 주입 → Playwright 캡처 → PNG 저장.

지시서 1-1:
- 1080x1080 PNG
- bottom-stack CSS (position absolute, bottom 74px, gap 16px)
- 사인오프는 본인/개인 브랜드명만 (GA명 금지)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import async_playwright


# ----------------------------------------------------------
# 카드 타입별 메인 콘텐츠 HTML 빌더
# ----------------------------------------------------------
def _accent(text: str, accent: str | None) -> str:
    """헤드라인 안에서 강조 단어를 <span class="accent">로 감싸기."""
    if not accent or accent not in text:
        return text
    return text.replace(accent, f'<span class="accent">{accent}</span>', 1)


def _build_main_html(card: dict) -> str:
    t = card.get("type", "")
    headline = card.get("headline", "")
    subhead = card.get("subhead", "")
    accent = card.get("accent", "")

    if t == "cover":
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="subhead">{subhead}</div>
        """

    if t == "problem":
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="subhead">{subhead}</div>
        """

    if t == "mistake":
        bad = card.get("bad_quote", "")
        explain = card.get("explain", "")
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="quote-box bad">
          <span class="label">SETTLER MENT</span>
          {bad}
        </div>
        <div class="subhead" style="margin-top:24px">{explain}</div>
        """

    if t == "before":
        bad = card.get("bad_quote", "")
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="quote-box bad">
          <span class="label">BEFORE</span>
          {bad}
        </div>
        """

    if t == "after":
        good = card.get("good_quote", "")
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="quote-box good">
          <span class="label">AFTER</span>
          {_accent(good, accent)}
        </div>
        """

    if t == "theory":
        author = card.get("author", "")
        quote = card.get("quote", "")
        explain = card.get("explain", "")
        return f"""
        <div class="theory-author">— {author}</div>
        <div class="theory-quote">"{quote}"</div>
        <div class="theory-explain">{explain}</div>
        """

    if t == "summary":
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="subhead">{subhead}</div>
        """

    if t == "cta":
        return f"""
        <div class="headline">{_accent(headline, accent)}</div>
        <div class="subhead">{subhead}</div>
        """

    # fallback
    return f'<div class="headline">{headline}</div><div class="subhead">{subhead}</div>'


def _build_top_label_block(card: dict) -> str:
    label = card.get("label", "")
    if not label:
        return ""
    # 라벨에 숫자 prefix 가 있으면 분리해서 골드로 표시
    parts = label.split(" ", 1)
    if len(parts) == 2 and parts[0].replace("0", "").isdigit() is False and parts[0].isdigit():
        return (
            f'<div class="top-label">'
            f'  <span class="num">{parts[0]}</span>'
            f'  <span>{parts[1]}</span>'
            f'</div>'
        )
    if len(parts) == 2 and parts[0].isdigit():
        return (
            f'<div class="top-label">'
            f'  <span class="num">{parts[0]}</span>'
            f'  <span>{parts[1]}</span>'
            f'</div>'
        )
    return f'<div class="top-label"><span>{label}</span></div>'


def _build_corner_quote_block(card: dict) -> str:
    if card.get("type") in ("theory", "summary"):
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
    # 폰트 로드 후 약간 대기
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
    p.add_argument("--out-dir", required=True, help="PNG 출력 디렉토리")
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args()

    with open(args.card_json, "r", encoding="utf-8") as f:
        card_set = json.load(f)

    paths = render_card_set(card_set, Path(args.out_dir), args.config)
    for path in paths:
        print(path)
