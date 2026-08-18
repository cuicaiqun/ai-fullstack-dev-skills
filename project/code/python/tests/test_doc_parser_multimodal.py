from __future__ import annotations

import asyncio
import sys
import types

from PIL import Image

from agents.doc_parser_agent import DocParserAgent


def _parser_without_llm() -> DocParserAgent:
    parser = object.__new__(DocParserAgent)
    parser.llm = None
    return parser


def test_image_parser_keeps_ocr_when_vision_fails(monkeypatch, tmp_path):
    image_path = tmp_path / "notice.png"
    Image.new("RGB", (1, 1), "white").save(image_path)
    parser = _parser_without_llm()

    monkeypatch.setattr(parser, "_ocr", lambda path: "Quarterly revenue: 12M")

    async def failing_vision(image):
        return ""

    monkeypatch.setattr(parser, "_safe_describe_image_with_llm", failing_vision)

    texts = asyncio.run(parser._parse_image(str(image_path)))

    assert texts == ["[图片 OCR]\nQuarterly revenue: 12M"]


def test_pdf_parser_adds_visual_text_for_pdf_with_extractable_text(monkeypatch, tmp_path):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.touch()
    parser = _parser_without_llm()

    class FakePage:
        def extract_text(self):
            return "Revenue report"

    class FakeReader:
        pages = [FakePage()]

    pypdf2 = types.ModuleType("PyPDF2")
    pypdf2.PdfReader = lambda path: FakeReader()
    monkeypatch.setitem(sys.modules, "PyPDF2", pypdf2)

    async def visual_content(path):
        return [
            "[PDF 第 1 页 OCR]\nRevenue grew 20%",
            "[PDF 第 1 页视觉理解]\nBar chart comparing quarterly revenue",
        ]

    monkeypatch.setattr(parser, "_pdf_vision_content", visual_content)

    texts = asyncio.run(parser._parse_pdf(str(pdf_path)))

    assert texts == [
        "Revenue report",
        "[PDF 第 1 页 OCR]\nRevenue grew 20%",
        "[PDF 第 1 页视觉理解]\nBar chart comparing quarterly revenue",
    ]
