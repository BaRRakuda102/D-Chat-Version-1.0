from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path


IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}

VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
}

DOCUMENT_TYPES = {
    "application/pdf",
    "text/plain",
    "application/json",
    "application/zip",
    "application/x-zip-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
}

ALLOWED_TYPES = IMAGE_TYPES | VIDEO_TYPES | DOCUMENT_TYPES


def is_allowed_content_type(content_type: str | None) -> bool:
    return bool(content_type and content_type in ALLOWED_TYPES)


def _replace_extension(file_name: str, extension: str) -> str:
    current = Path(file_name)
    stem = current.stem or "upload"
    return f"{stem}{extension}"


def _compress_video_bytes(content: bytes, file_name: str) -> tuple[bytes, str, str] | None:
    with tempfile.TemporaryDirectory(prefix="dchat-video-") as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / file_name
        output_path = temp_path / _replace_extension(file_name, ".mp4")
        input_path.write_bytes(content)

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=180,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        if completed.returncode != 0 or not output_path.exists():
            return None

        output_bytes = output_path.read_bytes()
        if not output_bytes or len(output_bytes) >= len(content):
            return None

        return output_bytes, output_path.name, "video/mp4"


async def prepare_upload(
    *,
    file_name: str,
    content_type: str | None,
    content: bytes,
) -> tuple[bytes, str, str]:
    normalized_type = content_type or "application/octet-stream"
    normalized_name = file_name or "upload"

    if normalized_type in VIDEO_TYPES:
        compressed = await asyncio.to_thread(_compress_video_bytes, content, normalized_name)
        if compressed:
            return compressed

    return content, normalized_name, normalized_type
