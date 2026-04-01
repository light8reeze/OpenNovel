from pathlib import Path


# Make absolute `app.*` imports resolve to the repository's `agent/app`
# package instead of an unrelated site-packages `app` distribution.
__path__ = [str(Path(__file__).resolve().parents[1] / "agent" / "app")]
