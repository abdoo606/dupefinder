from __future__ import annotations

import json
import os

import pytest

from dupefinder.report import human_size, to_human, to_json, to_shell_script
from dupefinder.scanner import DuplicateGroup, file_digest, find_duplicates, iter_files, plan_deletion


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "a.txt").write_text("hello world")
    (tmp_path / "b.txt").write_text("hello world")          # duplicate of a
    (tmp_path / "c.txt").write_text("different content")     # unique
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "d.txt").write_text("hello world")                # duplicate, nested
    (sub / ".hidden").write_text("hello world")              # hidden: skipped by default
    return tmp_path


def test_finds_the_expected_group(tree):
    groups = find_duplicates([tree])
    assert len(groups) == 1
    assert groups[0].size == len(b"hello world")
    assert len(groups[0].paths) == 3
    assert groups[0].wasted_bytes == 2 * len(b"hello world")


def test_hidden_files_are_skipped_by_default(tree):
    names = [p.name for p in iter_files([tree])]
    assert ".hidden" not in names


def test_hidden_files_included_when_asked(tree):
    names = [p.name for p in iter_files([tree], skip_hidden=False)]
    assert ".hidden" in names


def test_min_size_filters_small_files(tmp_path):
    (tmp_path / "x").write_text("1")
    (tmp_path / "y").write_text("1")
    assert find_duplicates([tmp_path], min_size=5) == []


def test_plan_deletion_keeps_one_per_group(tree):
    groups = find_duplicates([tree])
    doomed = plan_deletion(groups)
    assert len(doomed) == 2
    assert groups[0].keeper() not in doomed


def test_keeper_is_oldest_file(tree):
    groups = find_duplicates([tree])
    keeper = groups[0].keeper()
    oldest = min(groups[0].paths, key=lambda p: p.stat().st_mtime)
    assert keeper == oldest


def test_broken_symlink_does_not_crash(tmp_path):
    (tmp_path / "real.txt").write_text("data")
    os.symlink(tmp_path / "ghost.txt", tmp_path / "link.txt")
    assert isinstance(find_duplicates([tmp_path]), list)


def test_digest_is_stable(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"\x00\x01\x02" * 1000)
    assert file_digest(f) == file_digest(f)


def test_human_size():
    assert human_size(999) == "999 B"
    assert human_size(2048) == "2.0 KB"


def test_json_report_shape(tree):
    payload = json.loads(to_json(find_duplicates([tree])))
    assert payload["total_wasted_bytes"] > 0
    assert payload["groups"][0]["duplicates"]


def test_shell_script_quotes_paths(tmp_path):
    p = tmp_path / "a file with spaces.txt"
    q = tmp_path / "b.txt"
    p.write_text("1")
    q.write_text("1")
    os.utime(q, (0, 0))  # make q the oldest, so the spaced path is the one removed
    group = DuplicateGroup("x", 1, [p, q])
    assert "'" in to_shell_script([group])


def test_empty_report(tree):
    assert "no duplicate" in to_human([])
