import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import streamlit as st
import opendataloader_pdf


@dataclass
class ExtractedTable:
    index: int
    source: str
    html: str
    markdown: str
    rows: list[list[str]]


class TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._in_row = True
            self._current_row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._current_cell = []
        elif tag == "br" and self._in_cell:
            self._current_cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append(normalize_text("".join(self._current_cell)))
            self._current_cell = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = []
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def is_java_available() -> bool:
    return shutil.which("java") is not None


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_html_tables(html_text: str) -> list[str]:
    return re.findall(r"<table\b.*?</table>", html_text, flags=re.IGNORECASE | re.DOTALL)


def html_table_to_rows(html_table: str) -> list[list[str]]:
    parser = TableHTMLParser()
    parser.feed(html_table)
    return [row for row in parser.rows if any(cell for cell in row)]


def rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""

    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    escaped_rows = [
        [cell.replace("|", "\\|").replace("\n", " ").strip() for cell in row]
        for row in normalized_rows
    ]
    header = escaped_rows[0]
    separator = ["---"] * column_count
    body = escaped_rows[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def rows_to_html(rows: list[list[str]]) -> str:
    if not rows:
        return ""

    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    html_rows = []

    for row_index, row in enumerate(normalized_rows):
        tag = "th" if row_index == 0 else "td"
        cells = "".join(f"<{tag}>{escape(cell)}</{tag}>" for cell in row)
        html_rows.append(f"<tr>{cells}</tr>")

    return "<table>\n" + "\n".join(html_rows) + "\n</table>"


def extract_markdown_table_blocks(markdown_text: str) -> list[str]:
    blocks: list[str] = []
    current_block: list[str] = []

    for line in markdown_text.splitlines():
        if "|" in line.strip():
            current_block.append(line.rstrip())
        elif current_block:
            if len(current_block) >= 2:
                blocks.append("\n".join(current_block))
            current_block = []

    if len(current_block) >= 2:
        blocks.append("\n".join(current_block))

    return blocks


def markdown_table_to_rows(markdown_table: str) -> list[list[str]]:
    rows: list[list[str]] = []

    for line in markdown_table.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue

        cells = [cell.strip().replace("\\|", "|") for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)

    return rows


def parse_pdf_tables(input_path: str) -> list[ExtractedTable]:
    with tempfile.TemporaryDirectory() as output_dir:
        opendataloader_pdf.convert(
            input_path=input_path,
            output_dir=output_dir,
            format=["html", "markdown", "json"],
            quiet=True,
        )

        tables: list[ExtractedTable] = []
        for html_file in sorted(Path(output_dir).glob("*.html")):
            html_text = html_file.read_text(encoding="utf-8")
            for html_table in extract_html_tables(html_text):
                rows = html_table_to_rows(html_table)
                if not rows:
                    continue

                tables.append(
                    ExtractedTable(
                        index=len(tables) + 1,
                        source=html_file.name,
                        html=html_table,
                        markdown=rows_to_markdown(rows),
                        rows=rows,
                    )
                )

        if tables:
            return tables

        markdown_files = sorted(Path(output_dir).glob("*.md"))
        markdown_files.extend(sorted(Path(output_dir).glob("*.markdown")))

        for markdown_file in markdown_files:
            markdown_text = markdown_file.read_text(encoding="utf-8")
            for markdown_table in extract_markdown_table_blocks(markdown_text):
                rows = markdown_table_to_rows(markdown_table)
                if not rows:
                    continue

                tables.append(
                    ExtractedTable(
                        index=len(tables) + 1,
                        source=markdown_file.name,
                        html=rows_to_html(rows),
                        markdown=rows_to_markdown(rows),
                        rows=rows,
                    )
                )

        return tables


def rows_to_preview_records(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []

    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    return [
        {f"Column {column_index + 1}": cell for column_index, cell in enumerate(row)}
        for row in normalized_rows
    ]


def render_table_preview(table: ExtractedTable) -> None:
    st.caption(f"{table.source} · {len(table.rows)}행")
    st.dataframe(rows_to_preview_records(table.rows), hide_index=True, use_container_width=True)


def wrap_html_document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; margin: 16px 0; width: 100%; }}
    th, td {{ border: 1px solid #d0d7de; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def combine_tables(tables: list[ExtractedTable], output_format: str) -> str:
    sections = []

    for table in tables:
        title = f"Table {table.index}"
        if output_format == "HTML":
            sections.append(f"<h2>{escape(title)}</h2>\n{table.html}")
        else:
            sections.append(f"## {title}\n\n{table.markdown}")

    combined = "\n\n".join(sections)
    if output_format == "HTML":
        return wrap_html_document("Selected PDF Tables", combined)

    return combined


st.set_page_config(page_title="PDF Analyzer", layout="centered")
st.title("PDF Analyzer")

uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is None:
    st.info("PDF 파일을 업로드하면 분석 결과를 확인할 수 있습니다.")
elif not is_java_available():
    st.error(
        "PDF 파서 실행에 Java 런타임이 필요하지만 현재 Streamlit 실행 환경에서 "
        "`java` 명령을 찾을 수 없습니다.\n\n"
        "Streamlit Cloud 배포 시 저장소 루트의 `packages.txt`에 "
        "`default-jre-headless`가 포함되어 있는지 확인한 뒤 앱을 재부팅해 주세요."
    )
else:
    suffix = Path(uploaded_file.name).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name

    try:
        with st.spinner("PDF를 분석하는 중입니다..."):
            tables = parse_pdf_tables(tmp_path)

        st.subheader("Tables")

        if not tables:
            st.warning("업로드한 PDF에서 추출 가능한 테이블을 찾지 못했습니다.")
        else:
            table_options = {
                f"Table {table.index} · {len(table.rows)}행 · {table.source}": table
                for table in tables
            }
            selected_labels = st.multiselect(
                "미리 보고 내보낼 테이블을 선택하세요.",
                options=list(table_options.keys()),
                default=list(table_options.keys()),
            )
            selected_tables = [table_options[label] for label in selected_labels]

            output_format = st.radio(
                "출력 형식",
                options=["HTML", "Markdown"],
                horizontal=True,
            )

            for table in selected_tables:
                with st.expander(f"Table {table.index}", expanded=True):
                    render_table_preview(table)

                    if output_format == "HTML":
                        st.markdown(table.html, unsafe_allow_html=True)
                        st.download_button(
                            "HTML 내보내기",
                            data=wrap_html_document(f"Table {table.index}", table.html),
                            file_name=f"table-{table.index}.html",
                            mime="text/html",
                            key=f"download-html-{table.index}",
                        )
                    else:
                        st.markdown(table.markdown)
                        st.download_button(
                            "Markdown 내보내기",
                            data=table.markdown,
                            file_name=f"table-{table.index}.md",
                            mime="text/markdown",
                            key=f"download-markdown-{table.index}",
                        )

            if selected_tables:
                combined_output = combine_tables(selected_tables, output_format)
                extension = "html" if output_format == "HTML" else "md"
                mime_type = "text/html" if output_format == "HTML" else "text/markdown"
                st.download_button(
                    "선택한 테이블 전체 내보내기",
                    data=combined_output,
                    file_name=f"selected-tables.{extension}",
                    mime=mime_type,
                    type="primary",
                )

    except Exception as exc:
        st.error(f"PDF 파싱에 실패했습니다. 파일 형식 또는 내용 확인 후 다시 시도해 주세요.\n\n상세: {exc}")
    finally:
        os.unlink(tmp_path)
