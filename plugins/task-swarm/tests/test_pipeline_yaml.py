"""tests for task_swarm/_pipeline_yaml.py — pipeline.yml YAML-subset parser."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm._pipeline_yaml import parse, PipelineYamlError  # noqa: E402


# --- Step A: block map + scalars ---

def test_flat_map_scalars():
    text = "version: 1\nname: hello\nflag: true\nempty:\n"
    assert parse(text) == {"version": 1, "name": "hello", "flag": True, "empty": None}


def test_nested_map():
    text = "run:\n  spec_id: user-login\n  max_parallel: 4\n"
    assert parse(text) == {"run": {"spec_id": "user-login", "max_parallel": 4}}


def test_bool_only_true_false_not_yes():
    assert parse("a: yes\nb: no\nc: on\n") == {"a": "yes", "b": "no", "c": "on"}


# --- Step B: block list + nesting ---

def test_block_list_of_scalars():
    assert parse("items:\n  - a\n  - b\n") == {"items": ["a", "b"]}


def test_list_of_maps():
    text = "task_groups:\n  - id: g1\n    name: A\n  - id: g2\n    name: B\n"
    assert parse(text) == {"task_groups": [{"id": "g1", "name": "A"}, {"id": "g2", "name": "B"}]}


def test_deep_nest_map_list_map():
    text = "task_groups:\n  - id: g1\n    tasks:\n      - id: g1.1\n        title: t\n"
    assert parse(text) == {"task_groups": [{"id": "g1", "tasks": [{"id": "g1.1", "title": "t"}]}]}


# --- Step C: flow list + quoted strings + comments ---

def test_flow_list():
    assert parse("writes: [a.py, b.py]\n") == {"writes": ["a.py", "b.py"]}
    assert parse("empty: []\n") == {"empty": []}


def test_quoted_string_with_colon():
    assert parse('name: "Q01: 接口"\n') == {"name": "Q01: 接口"}
    assert parse("name: 'a: b'\n") == {"name": "a: b"}


def test_comment_full_and_inline():
    assert parse("# header\nversion: 1  # trailing\nname: a\n") == {"version": 1, "name": "a"}


def test_hash_inside_quotes_not_comment():
    assert parse('name: "a # b"\n') == {"name": "a # b"}


# --- Step D: explicit errors for out-of-subset constructs ---

@pytest.mark.parametrize("text, frag", [
    ("desc: |\n  multi\n", "block scalar"),
    ("desc: >\n  folded\n", "block scalar"),
    ("review: {reviewer: true}\n", "flow map"),
    ("a: &anchor 1\n", "anchor"),
    ("a: *ref\n", "alias"),
    ("---\nversion: 1\n", "multi-document"),
    ("name: !!str x\n", "tag"),
    ("writes: [[a], [b]]\n", "nested flow"),
])
def test_unsupported_constructs_raise(text, frag):
    with pytest.raises(PipelineYamlError) as e:
        parse(text)
    assert frag in str(e.value).lower() and "line" in str(e.value).lower()


def test_tab_indent_raises():
    with pytest.raises(PipelineYamlError):
        parse("run:\n\tspec_id: x\n")


def test_merge_key_raises():
    with pytest.raises(PipelineYamlError):
        parse("a: 1\n<<: *x\n")


def test_odd_indent_raises():
    with pytest.raises(PipelineYamlError):
        parse("run:\n   spec_id: x\n")  # 3-space indent


def test_quoted_special_chars_not_raise():
    assert parse('name: "a & b"\n') == {"name": "a & b"}
    assert parse('name: "*x"\n') == {"name": "*x"}
    assert parse('name: "| pipe"\n') == {"name": "| pipe"}
