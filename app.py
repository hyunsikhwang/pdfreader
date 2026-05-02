"""Simple UI helpers for displaying parsed PDF results with a minimal UX."""

from __future__ import annotations

from typing import Any

# UI에 표시할 최소 출력 필드(schema)
MINIMAL_OUTPUT_FIELDS = [
    "filename",
    "num_pages",
    "extracted_text_preview",
    "tables_count",
    "metadata",
]

TEXT_PREVIEW_LIMIT = 1000


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_pdf_result(result: Any) -> dict[str, Any]:
    """파서의 다양한 반환 타입을 UI 표시용 공통 구조로 정규화한다."""
    data = result if isinstance(result, dict) else {"raw": result}

    filename = data.get("filename") or data.get("file_name") or "unknown.pdf"
    num_pages = data.get("num_pages") or data.get("pages") or 0
    extracted_text = (
        data.get("extracted_text")
        or data.get("text")
        or data.get("content")
        or ""
    )
    tables = data.get("tables")
    tables_count = data.get("tables_count")
    if tables_count is None:
        tables_count = len(tables) if isinstance(tables, list) else 0

    metadata = data.get("metadata")
    if metadata is None:
        metadata = {
            k: v
            for k, v in data.items()
            if k not in {"filename", "file_name", "num_pages", "pages", "extracted_text", "text", "content", "tables", "tables_count"}
        }

    preview = _stringify(extracted_text)[:TEXT_PREVIEW_LIMIT]

    return {
        "filename": filename,
        "num_pages": num_pages,
        "extracted_text_preview": preview,
        "tables_count": tables_count,
        "metadata": metadata,
        "raw": data,
    }


def build_display_sections(result: Any) -> dict[str, Any]:
    """미니멀 UX 원칙에 맞춰 표시 순서를 고정한다.

    순서:
      1) 파일 정보
      2) 핵심 요약
      3) 상세(raw json) 토글
    """
    normalized = normalize_pdf_result(result)

    file_info = {
        "filename": normalized["filename"],
        "num_pages": normalized["num_pages"],
    }
    summary = {
        "extracted_text_preview": normalized["extracted_text_preview"],
        "tables_count": normalized["tables_count"],
        "metadata": normalized["metadata"],
    }

    return {
        "schema": MINIMAL_OUTPUT_FIELDS,
        "file_info": file_info,
        "summary": summary,
        "raw_json": normalized["raw"],
    }
