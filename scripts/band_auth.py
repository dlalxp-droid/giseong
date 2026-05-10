"""
band_auth.py
============
네이버 밴드 Open API OAuth2 헬퍼.

주요 기능:
  - access_token 의 만료를 확인 (간단한 self-test 호출)
  - refresh_token 으로 access_token 재발급
  - 사용자가 가입한 밴드 목록 조회 (band_key 확인용)

공식 OAuth2 엔드포인트:
  authorize : https://auth.band.us/oauth2/authorize
  token     : https://auth.band.us/oauth2/token

client_credentials 는 지원되지 않으며, 최초 1회 브라우저로 authorize
페이지를 거쳐 redirect_uri 에 전달된 code 를 받아 token 으로 교환해야 한다.
"""

from __future__ import annotations

import base64
import os
import sys
from typing import Optional

import requests

BAND_AUTH_BASE = "https://auth.band.us"
BAND_OPENAPI_BASE = "https://openapi.band.us"


def _basic_auth_header(client_id: str, client_secret: str) -> dict:
    raw = f"{client_id}:{client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def build_authorize_url(client_id: str, redirect_uri: str) -> str:
    """브라우저에서 한 번 띄울 동의화면 URL."""
    return (
        f"{BAND_AUTH_BASE}/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=READ_BAND,READ_POST,WRITE_POST"
    )


def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """authorize 화면에서 받은 code 를 token 으로 교환."""
    r = requests.get(
        f"{BAND_AUTH_BASE}/oauth2/token",
        params={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers=_basic_auth_header(client_id, client_secret),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def refresh_access_token(
    refresh_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> dict:
    """refresh_token 으로 access_token 갱신."""
    refresh_token = refresh_token or os.environ["BAND_REFRESH_TOKEN"]
    client_id = client_id or os.environ["BAND_CLIENT_ID"]
    client_secret = client_secret or os.environ["BAND_CLIENT_SECRET"]

    r = requests.get(
        f"{BAND_AUTH_BASE}/oauth2/token",
        params={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers=_basic_auth_header(client_id, client_secret),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def list_bands(access_token: Optional[str] = None) -> list[dict]:
    """사용자가 속한 밴드 목록. band_key, name 등 반환."""
    access_token = access_token or os.environ["BAND_ACCESS_TOKEN"]
    r = requests.get(
        f"{BAND_OPENAPI_BASE}/v2.1/bands",
        params={"access_token": access_token},
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("result_code") != 1:
        raise RuntimeError(f"list_bands failed: {j}")
    return j["result_data"]["bands"]


def ping(access_token: Optional[str] = None) -> bool:
    """토큰이 유효한지 가벼운 호출로 확인."""
    try:
        list_bands(access_token)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    import argparse, json

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("authorize-url")

    p_ex = sub.add_parser("exchange")
    p_ex.add_argument("--code", required=True)

    sub.add_parser("refresh")
    sub.add_parser("bands")
    sub.add_parser("ping")

    args = p.parse_args()

    if args.cmd == "authorize-url":
        print(build_authorize_url(
            os.environ["BAND_CLIENT_ID"],
            os.environ["BAND_REDIRECT_URI"],
        ))
    elif args.cmd == "exchange":
        print(json.dumps(exchange_code_for_token(
            args.code,
            os.environ["BAND_CLIENT_ID"],
            os.environ["BAND_CLIENT_SECRET"],
            os.environ["BAND_REDIRECT_URI"],
        ), ensure_ascii=False, indent=2))
    elif args.cmd == "refresh":
        print(json.dumps(refresh_access_token(), ensure_ascii=False, indent=2))
    elif args.cmd == "bands":
        for b in list_bands():
            print(f"{b.get('band_key')}\t{b.get('name')}")
    elif args.cmd == "ping":
        ok = ping()
        print("OK" if ok else "INVALID")
        sys.exit(0 if ok else 1)
