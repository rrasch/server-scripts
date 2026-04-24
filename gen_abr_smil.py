#!/usr/bin/env python3

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
from lxml import etree as ET
from xml.etree.ElementTree import Element, SubElement, ElementTree


BASENAME_RE = re.compile(r"_(\d+)k.*\.mp4$")


def derive_basename(filepath: str):
    """
    Derive a logical ABR basename from a rendition filename.

    This removes the bitrate suffix and trailing descriptor.

    Example:
        /path/video_1500k_s.mp4 -> /path/video

    Returns:
        str or None: Normalized basename used for grouping, or None
        if the filename does not match the expected pattern.
    """
    match = BASENAME_RE.search(filepath)
    if not match:
        return None
    return filepath[: match.start()]


def run_ffprobe(filepath: str) -> dict:
    """
    Execute ffprobe and return parsed JSON metadata.

    Uses ffprobe to extract stream and format-level metadata
    required for SMIL generation.

    Args:
        filepath (str): Path to media file.

    Returns:
        dict: Parsed ffprobe JSON output.

    Raises:
        RuntimeError: If ffprobe execution fails.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        filepath,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {filepath}")

    return json.loads(result.stdout)


def extract_stream_info(filepath: str):
    """
    Extract required video/audio metadata for ABR SMIL generation.

    This function enforces strict validation:
    - Video stream must exist
    - Audio stream must exist
    - Video bitrate must be present and non-zero
    - Audio bitrate must be present and non-zero

    Args:
        filepath (str): Path to media file.

    Returns:
        dict: Dictionary containing:
            - file (str)
            - width (int)
            - height (int)
            - video_bitrate (int)
            - audio_bitrate (int)

    Raises:
        RuntimeError: If required streams or bitrates are missing.
    """
    data = run_ffprobe(filepath)

    video = None
    audio = None

    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not video:
            video = s
        elif s.get("codec_type") == "audio" and not audio:
            audio = s

    if not video:
        raise RuntimeError(f"No video stream found: {filepath}")

    if not audio:
        raise RuntimeError(f"No audio stream found (required): {filepath}")

    width = video.get("width")
    height = video.get("height")

    video_bitrate = video.get("bit_rate")
    audio_bitrate = audio.get("bit_rate")

    if video_bitrate is None or int(video_bitrate) <= 0:
        raise RuntimeError(f"Missing video bitrate: {filepath}")

    if audio_bitrate is None or int(audio_bitrate) <= 0:
        raise RuntimeError(f"Missing audio bitrate: {filepath}")

    return {
        "file": filepath,
        "width": width,
        "height": height,
        "video_bitrate": int(video_bitrate),
        "audio_bitrate": int(audio_bitrate),
    }


def find_basenames_from_directory(root_dir: str):
    """
    Recursively scan a directory and extract ABR basenames.

    This walks all subdirectories, finds MP4 files, and groups them
    by stripping bitrate suffix patterns.

    Args:
        root_dir (str): Root directory to scan.

    Returns:
        set: Unique set of derived basenames.
    """
    basenames = set()

    for dirpath, _, files in os.walk(root_dir):
        for name in files:
            if not name.lower().endswith(".mp4"):
                continue

            full = os.path.join(dirpath, name)
            base = derive_basename(full)

            if base:
                basenames.add(base)

    return basenames


def find_renditions(basename, exclude=None):
    """
    Find and parse all valid ABR renditions for a given basename.

    This function:
    - Glob-matches MP4 files using `{basename}_*.mp4`
    - Excludes files containing the `exclude` substring (if provided)
    - Extracts metadata using `extract_stream_info`
    - Sorts results by video bitrate (ascending)

    Args:
        basename (str):
            Logical base path for a rendition group.

        exclude (str or None):
            Substring used to filter out unwanted renditions before probing.
            If None, no filtering is applied.

    Returns:
        list of dict:
            Each dictionary contains:
                - file (str)
                - width (int)
                - height (int)
                - video_bitrate (int)
                - audio_bitrate (int)

    Raises:
        RuntimeError:
            If no valid renditions are found.
    """
    pattern = f"{basename}_*.mp4"
    files = glob.glob(pattern)

    renditions = []

    for f in files:
        if exclude and exclude in f:
            continue

        try:
            renditions.append(extract_stream_info(f))
        except Exception as e:
            print("Skipping {}: {}".format(f, e))

    if not renditions:
        raise RuntimeError("No valid renditions for {}".format(basename))

    renditions.sort(key=lambda x: x["video_bitrate"])
    return renditions


def _build_smil(renditions, output_file: str):
    """
    Generate a Wowza-compatible SMIL file from renditions.

    Creates an XML SMIL document containing adaptive bitrate
    video entries sorted by bitrate.

    Args:
        renditions (list[dict]): Parsed rendition metadata.
        output_file (str): Destination SMIL file path.

    Returns:
        None
    """
    smil = Element("smil")
    smil.set("title", "")

    body = SubElement(smil, "body")
    switch = SubElement(body, "switch")

    for r in renditions:
        video = SubElement(switch, "video")
        video.set("src", os.path.basename(r["file"]))
        video.set("width", str(r["width"]))
        video.set("height", str(r["height"]))
        video.set("systemLanguage", "eng")

        vp = SubElement(video, "param")
        vp.set("name", "videoBitrate")
        vp.set("value", str(r["video_bitrate"]))
        vp.set("valuetype", "data")

        ap = SubElement(video, "param")
        ap.set("name", "audioBitrate")
        ap.set("value", str(r["audio_bitrate"]))
        ap.set("valuetype", "data")

    ElementTree(smil).write(output_file, encoding="utf-8", xml_declaration=True)


def build_smil(renditions, output_file: str):
    """
    Generate a Wowza-compatible SMIL file from renditions.

    Creates an XML SMIL document containing adaptive bitrate
    video entries sorted by bitrate.

    Args:
        renditions (list[dict]): Parsed rendition metadata.
        output_file (str): Destination SMIL file path.

    Returns:
        None
    """
    smil = ET.Element("smil", title="")
    body = ET.SubElement(smil, "body")
    switch = ET.SubElement(body, "switch")

    for r in renditions:
        video = ET.SubElement(switch, "video")
        video.set("src", os.path.basename(r["file"]))
        video.set("width", str(r["width"]))
        video.set("height", str(r["height"]))
        video.set("systemLanguage", "eng")

        vp = ET.SubElement(video, "param")
        vp.set("name", "videoBitrate")
        vp.set("value", str(r["video_bitrate"]))
        vp.set("valuetype", "data")

        ap = ET.SubElement(video, "param")
        ap.set("name", "audioBitrate")
        ap.set("value", str(r["audio_bitrate"]))
        ap.set("valuetype", "data")

    tree = ET.ElementTree(smil)

    tree.write(
        output_file,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )


def check_ffprobe_available():
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found in PATH. Install FFmpeg.")


def main():
    """
    Entry point for SMIL generation.

    Supports:
    - Directory input (recursive scan)
    - Single basename input

    Generates one SMIL file per detected ABR group.
    """
    check_ffprobe_available()

    parser = argparse.ArgumentParser(
        description="Generate Wowza SMIL files from directory or basename"
    )

    parser.add_argument("input", help="Directory or basename")
    parser.add_argument("-o", "--output-dir", help="Output directory")

    args = parser.parse_args()

    if os.path.isdir(args.input):
        basenames = find_basenames_from_directory(args.input)
    else:
        basenames = {args.input}

    if not basenames:
        raise RuntimeError("No basenames found")

    for base in sorted(basenames):
        print(f"\nProcessing: {base}")

        try:
            renditions = find_renditions(base, exclude="mobile")

            out_dir = args.output_dir or os.path.dirname(base)
            os.makedirs(out_dir, exist_ok=True)

            out_file = os.path.join(out_dir, os.path.basename(base) + ".smil")

            build_smil(renditions, out_file)

            print(f"  -> {out_file}")

        except Exception as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
