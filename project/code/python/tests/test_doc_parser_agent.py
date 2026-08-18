from __future__ import annotations

import asyncio

from agents.doc_parser_agent import DocParserAgent, DocType


def _parser_without_llm() -> DocParserAgent:
    parser = object.__new__(DocParserAgent)
    parser.llm = None
    return parser


def test_parse_markdown_happy_path_chunks_and_stable_doc_id(tmp_path):
    path = tmp_path / "handbook.md"
    path.write_text("企业知识库支持混合检索。\n" * 40, encoding="utf-8")

    parser = _parser_without_llm()
    chunks = asyncio.run(parser.parse(str(path)))

    assert chunks
    assert all(c.doc_type == DocType.MARKDOWN for c in chunks)
    assert all(c.doc_id == DocParserAgent._make_doc_id(str(path)) for c in chunks)
    assert chunks[0].chunk_id == f"{chunks[0].doc_id}#chunk-0"
    assert "企业知识库" in chunks[0].content


def test_parse_csv_table_happy_path(tmp_path):
    path = tmp_path / "employees.csv"
    path.write_text("name,dept\nAlice,AI\nBob,Infra\n", encoding="utf-8")

    parser = _parser_without_llm()
    chunks = asyncio.run(parser.parse(str(path)))

    assert chunks
    assert chunks[0].doc_type == DocType.TABLE
    assert "Alice" in chunks[0].content
    assert "dept: AI" in chunks[0].content


def test_normalize_path_and_doc_id_are_stable_for_relative_paths(tmp_path, monkeypatch):
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    relative_id = DocParserAgent._make_doc_id("note.txt")
    absolute_id = DocParserAgent._make_doc_id(str(path.resolve()))
    assert relative_id == absolute_id
    assert DocParserAgent.normalize_path("note.txt") == str(path.resolve())
