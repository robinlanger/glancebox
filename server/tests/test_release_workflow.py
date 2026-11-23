"""A pre-release (VERSION with a suffix, e.g. 0.7.0-beta.1) must never become :latest or the
latest GitHub release. Checked on the workflow text, since the workflow only runs on a tag."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


def text() -> str:
    return WORKFLOW.read_text()


def test_suffixed_version_is_a_prerelease():
    t = text()
    assert '*-*) echo "PRERELEASE=true"' in t
    assert '*) echo "PRERELEASE=false"' in t


def test_latest_tag_only_for_final_releases():
    t = text()
    assert "${{ env.IMAGE }}:latest" not in t
    assert "env.PRERELEASE != 'true' && format('{0}:latest', env.IMAGE)" in t


def test_github_release_marked_as_prerelease():
    t = text()
    assert 'pre=(--prerelease)' in t and '"${pre[@]}"' in t
