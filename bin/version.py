#!/usr/bin/env python3
import os, subprocess, pathlib

def get_version() -> str:
    """
    Use `git describe` with a tag match pattern (defaults to semver).
    Falls back to ENV ESPN4CC_VERSION, then a static string.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[1]  # project root
    tag_match = os.getenv("ESPN4CC_TAG_MATCH", r"v[0-9]+\.[0-9]+(\.[0-9]+)?" )  # semver only
    try:
        cmd = ["git","-C", str(repo_root), "describe", "--tags", "--long", "--dirty", "--always", "--match", tag_match]
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return os.getenv("ESPN4CC_VERSION", "v0.0.0+local")

# convenience constant
VERSION = get_version()

if __name__ == "__main__":
    print(VERSION)
