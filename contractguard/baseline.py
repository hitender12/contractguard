"""Baseline management: compare against a file or a git ref.

Baselines come from one of:
- a file on disk (``--base path/to/spec.yaml``)
- a git ref + path (``--base-ref main --base-path api/openapi.yaml``),
  resolved with ``git show <ref>:<path>``
- the same file at a git ref (``--base-ref HEAD~1 --head path/to/spec.yaml``)
"""

from __future__ import annotations

import subprocess

from .parser import SpecError, parse_spec_file, parse_spec_text


def spec_from_git(ref: str, path: str, repo: str | None = None):
    """Return the spec text at ``ref:path`` using the git CLI."""
    cmd = ["git"]
    if repo:
        cmd += ["-C", repo]
    cmd += ["show", f"{ref}:{path}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as exc:
        raise SpecError("git CLI not found; cannot resolve a git baseline") from exc
    except subprocess.TimeoutExpired as exc:
        raise SpecError(f"git show timed out for {ref}:{path}") from exc
    if result.returncode != 0:
        raise SpecError(
            f"git show {ref}:{path} failed: {result.stderr.strip() or 'unknown error'}"
        )
    return result.stdout


def load_base(*, base_file: str | None, base_ref: str | None, base_path: str | None):
    """Load the baseline contract from a file or a git ref."""
    if base_file:
        return parse_spec_file(base_file), base_file
    if base_ref and base_path:
        text = spec_from_git(base_ref, base_path)
        return parse_spec_text(text, f"{base_ref}:{base_path}"), f"{base_ref}:{base_path}"
    raise SpecError(
        "no baseline given: pass --base <file> or --base-ref <ref> --base-path <path>"
    )


def load_head(*, head_file: str | None, head_ref: str | None, head_path: str | None):
    """Load the head contract from a file or a git ref."""
    if head_file:
        return parse_spec_file(head_file), head_file
    if head_ref and head_path:
        text = spec_from_git(head_ref, head_path)
        return parse_spec_text(text, f"{head_ref}:{head_path}"), f"{head_ref}:{head_path}"
    raise SpecError(
        "no head given: pass --head <file> or --head-ref <ref> --head-path <path>"
    )
