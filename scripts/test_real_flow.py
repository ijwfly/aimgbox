#!/usr/bin/env python3
"""
Test real Replicate provider: remove_bg + img2img.

Expects:
  - docker-compose up -d
  - uv run alembic upgrade head
  - REPLICATE_API_TOKEN=... uv run python -m aimg seed
  - API + worker running (uv run python -m aimg api & uv run python -m aimg worker &)

Usage:
  AIMG_API_KEY=<jwt-from-seed> uv run python scripts/test_real_flow.py

  Optional: pass a real image path as argument (default: generates a test PNG).
  AIMG_API_KEY=<jwt> uv run python scripts/test_real_flow.py photo.jpg
"""
import asyncio
import os
import struct
import sys
import zlib

import httpx

API_BASE = os.environ.get("AIMG_API_BASE", "http://localhost:8010")
API_KEY = os.environ.get("AIMG_API_KEY", "")


def _make_test_png(width: int = 256, height: int = 256) -> bytes:
    """Generate a minimal valid PNG with a red/blue gradient."""

    def _raw_data() -> bytes:
        rows = []
        for y in range(height):
            row = b"\x00"  # filter: none
            for x in range(width):
                r = int(255 * x / width)
                g = 0
                b = int(255 * y / height)
                row += struct.pack("BBB", r, g, b)
            rows.append(row)
        return b"".join(rows)

    raw = _raw_data()
    compressed = zlib.compress(raw)

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    return png


def _load_image(path: str | None) -> tuple[bytes, str, str]:
    """Return (data, filename, content_type)."""
    if path and os.path.isfile(path):
        ext = os.path.splitext(path)[1].lower()
        ct_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        ct = ct_map.get(ext, "image/png")
        with open(path, "rb") as f:
            return f.read(), os.path.basename(path), ct
    return _make_test_png(), "test.png", "image/png"


async def _upload(
    client: httpx.AsyncClient,
    headers: dict,
    img_data: bytes,
    filename: str,
    content_type: str,
) -> str:
    resp = await client.post(
        "/v1/files",
        headers={k: v for k, v in headers.items() if k != "Content-Type"},
        files={"file": (filename, img_data, content_type)},
    )
    if resp.status_code != 201:
        print(f"  FAIL upload: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)
    file_id = resp.json()["data"]["file_id"]
    print(f"  Uploaded: {file_id} ({len(img_data)} bytes, {filename})")
    return file_id


async def _create_job(
    client: httpx.AsyncClient,
    headers: dict,
    job_type: str,
    input_data: dict,
) -> str:
    resp = await client.post(
        "/v1/jobs",
        headers=headers,
        json={"job_type": job_type, "input": input_data},
    )
    if resp.status_code not in (200, 201):
        print(f"  FAIL create: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)
    job_id = resp.json()["data"]["job_id"]
    print(f"  Job created: {job_id}")
    return job_id


async def _poll(
    client: httpx.AsyncClient,
    headers: dict,
    job_id: str,
    timeout: int = 120,
) -> dict:
    for i in range(timeout):
        await asyncio.sleep(1)
        resp = await client.get(f"/v1/jobs/{job_id}", headers=headers)
        data = resp.json()["data"]
        status = data["status"]
        sys.stdout.write(f"\r  Polling... {status} ({i + 1}s)")
        sys.stdout.flush()
        if status in ("succeeded", "failed"):
            print()
            return data
    print("\n  TIMEOUT")
    sys.exit(1)


async def _download_result(
    client: httpx.AsyncClient,
    headers: dict,
    job_id: str,
    out_path: str,
) -> None:
    resp = await client.get(f"/v1/jobs/{job_id}/result", headers=headers)
    if resp.status_code != 200:
        print(f"  FAIL result: {resp.status_code} {resp.text[:300]}")
        return
    url = resp.json()["data"]["download_url"]
    dl = await client.get(url)
    dl.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(dl.content)
    print(f"  Saved: {out_path} ({len(dl.content)} bytes)")


async def main() -> None:
    if not API_KEY:
        print("Set AIMG_API_KEY env var (JWT from `aimg seed` output)")
        sys.exit(1)

    image_path = sys.argv[1] if len(sys.argv) > 1 else None
    img_data, filename, content_type = _load_image(image_path)

    headers = {
        "X-API-Key": API_KEY,
        "X-External-User-Id": "real-flow-test",
        "Content-Type": "application/json",
    }

    os.makedirs("output", exist_ok=True)

    async with httpx.AsyncClient(
        base_url=API_BASE, timeout=300
    ) as client:
        # Health check
        resp = await client.get("/health")
        if resp.status_code != 200:
            print(f"API not healthy: {resp.status_code}")
            sys.exit(1)
        print("API is healthy\n")

        # Upload image
        print("[1/4] Uploading image...")
        file_id = await _upload(
            client, headers, img_data, filename, content_type
        )

        # remove_bg
        print("\n[2/4] Testing remove_bg...")
        job_id = await _create_job(
            client, headers, "remove_bg", {"image": file_id}
        )
        result = await _poll(client, headers, job_id)
        if result["status"] == "succeeded":
            await _download_result(
                client, headers, job_id, "output/remove_bg_result.png"
            )
            print("  remove_bg: OK")
        else:
            print(f"  remove_bg: FAILED — {result.get('error')}")

        # Wait for Replicate rate limit to reset (free tier: 6 req/min)
        print("\n  Waiting 15s for rate limit reset...")
        await asyncio.sleep(15)

        # img2img
        print("\n[3/4] Testing img2img...")
        job_id = await _create_job(
            client,
            headers,
            "img2img",
            {
                "image": file_id,
                "prompt": "turn this into a watercolor painting",
            },
        )
        result = await _poll(client, headers, job_id)
        if result["status"] == "succeeded":
            await _download_result(
                client, headers, job_id, "output/img2img_result.png"
            )
            print("  img2img: OK")
        else:
            print(f"  img2img: FAILED — {result.get('error')}")

        # Wait for rate limit reset
        print("\n  Waiting 15s for rate limit reset...")
        await asyncio.sleep(15)

        # txt2img
        print("\n[4/4] Testing txt2img...")
        job_id = await _create_job(
            client,
            headers,
            "txt2img",
            {"prompt": "a cat sitting on the moon"},
        )
        result = await _poll(client, headers, job_id)
        if result["status"] == "succeeded":
            await _download_result(
                client, headers, job_id, "output/txt2img_result.png"
            )
            print("  txt2img: OK")
        else:
            print(f"  txt2img: FAILED — {result.get('error')}")

    print("\n=== Done. Check output/ folder for results. ===")


if __name__ == "__main__":
    asyncio.run(main())
