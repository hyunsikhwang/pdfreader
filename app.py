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
from pypdf import PdfReader


@dataclass
class ExtractedTable:
    index: int
    source: str
    html: str
    markdown: str
    rows: list[list[str]]


@dataclass
class PdfSection:
    index: int
    title: str
    start_page: int
    end_page: int
    level: int
    source: str


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


def parse_page_numbers(value: str) -> set[int]:
    pages: set[int] = set()

    for chunk in value.split(","):
        part = chunk.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if start_text.strip().isdigit() and end_text.strip().isdigit():
                start_page = int(start_text)
                end_page = int(end_text)
                if start_page <= end_page:
                    pages.update(range(start_page, end_page + 1))
            continue

        if part.isdigit():
            pages.add(int(part))

    return pages


def compact_page_numbers(pages: set[int]) -> str:
    if not pages:
        return ""

    sorted_pages = sorted(pages)
    ranges: list[str] = []
    start = previous = sorted_pages[0]

    for page in sorted_pages[1:]:
        if page == previous + 1:
            previous = page
            continue

        ranges.append(f"{start}-{previous}" if start != previous else str(start))
        start = previous = page

    ranges.append(f"{start}-{previous}" if start != previous else str(start))
    return ",".join(ranges)


def flatten_pdf_outline(reader: PdfReader) -> list[tuple[str, int, int]]:
    outline_items: list[tuple[str, int, int]] = []

    def walk(items: object, level: int) -> None:
        if not isinstance(items, list):
            return

        for item in items:
            if isinstance(item, list):
                walk(item, level + 1)
                continue

            title = normalize_text(str(getattr(item, "title", "")))
            if not title:
                continue

            try:
                page_number = reader.get_destination_page_number(item) + 1
            except Exception:
                continue

            outline_items.append((title, page_number, level))

    try:
        walk(reader.outline, 0)
    except Exception:
        return []

    return outline_items


def first_meaningful_page_line(text: str, page_number: int) -> str:
    for line in text.splitlines()[:20]:
        candidate = normalize_text(line)
        if 4 <= len(candidate) <= 120:
            return candidate

    return f"{page_number}페이지"


def infer_sections_from_pages(reader: PdfReader, max_pages: int = 80) -> list[PdfSection]:
    sections: list[PdfSection] = []
    page_count = len(reader.pages)

    for page_index, page in enumerate(reader.pages[:max_pages]):
        page_number = page_index + 1
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        title = first_meaningful_page_line(text, page_number)
        sections.append(
            PdfSection(
                index=len(sections) + 1,
                title=title,
                start_page=page_number,
                end_page=page_number,
                level=0,
                source="페이지 제목 추정",
            )
        )

    if page_count > max_pages:
        sections.append(
            PdfSection(
                index=len(sections) + 1,
                title=f"{max_pages + 1}-{page_count}페이지",
                start_page=max_pages + 1,
                end_page=page_count,
                level=0,
                source="페이지 범위",
            )
        )

    return sections


def extract_pdf_sections(input_path: str) -> list[PdfSection]:
    reader = PdfReader(input_path)
    page_count = len(reader.pages)
    outline_items = flatten_pdf_outline(reader)

    if outline_items:
        sections: list[PdfSection] = []
        for item_index, (title, start_page, level) in enumerate(outline_items):
            next_pages = [
                page
                for _, page, next_level in outline_items[item_index + 1 :]
                if next_level <= level and page >= start_page
            ]
            end_page = (min(next_pages) - 1) if next_pages else page_count
            end_page = max(start_page, min(end_page, page_count))
            sections.append(
                PdfSection(
                    index=len(sections) + 1,
                    title=title,
                    start_page=start_page,
                    end_page=end_page,
                    level=level,
                    source="PDF 내장 목차",
                )
            )

        return sections

    return infer_sections_from_pages(reader)


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


def parse_pdf_tables(input_path: str, pages: str | None = None) -> list[ExtractedTable]:
    with tempfile.TemporaryDirectory() as output_dir:
        opendataloader_pdf.convert(
            input_path=input_path,
            output_dir=output_dir,
            format=["html", "markdown"],
            quiet=True,
            pages=pages,
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


def rows_to_preview_records_limited(
    rows: list[list[str]],
    max_rows: int = 5,
    max_columns: int = 6,
) -> list[dict[str, str]]:
    records = rows_to_preview_records(rows[:max_rows])
    return [
        {
            column: shorten_text(value, 80)
            for column, value in list(record.items())[:max_columns]
        }
        for record in records
    ]


def shorten_text(value: str, max_length: int = 120) -> str:
    text = normalize_text(value)
    if len(text) <= max_length:
        return text

    return text[: max_length - 1] + "…"


def table_dimensions(table: ExtractedTable) -> tuple[int, int]:
    if not table.rows:
        return 0, 0

    return len(table.rows), max(len(row) for row in table.rows)


def table_fingerprint(table: ExtractedTable) -> str:
    cells: list[str] = []
    for row in table.rows[:4]:
        for cell in row[:4]:
            text = normalize_text(cell)
            if text:
                cells.append(text)

    if not cells:
        return "내용 미리보기가 없습니다."

    return shorten_text(" · ".join(cells), 180)


def table_option_label(table: ExtractedTable) -> str:
    row_count, column_count = table_dimensions(table)
    return f"Table {table.index} · {row_count}행 x {column_count}열 · {table_fingerprint(table)}"


def section_option_label(section: PdfSection) -> str:
    indent = "  " * min(section.level, 3)
    page_range = (
        str(section.start_page)
        if section.start_page == section.end_page
        else f"{section.start_page}-{section.end_page}"
    )
    return f"{indent}{section.index}. {section.title} · p.{page_range}"


def pages_from_sections(sections: list[PdfSection]) -> str:
    pages: set[int] = set()

    for section in sections:
        pages.update(range(section.start_page, section.end_page + 1))

    return compact_page_numbers(pages)


def render_section_index(sections: list[PdfSection]) -> None:
    preview_rows = []
    for section in sections[:80]:
        page_range = (
            str(section.start_page)
            if section.start_page == section.end_page
            else f"{section.start_page}-{section.end_page}"
        )
        preview_rows.append(
            {
                "항목": section.index,
                "제목": ("  " * min(section.level, 3)) + shorten_text(section.title, 100),
                "페이지": page_range,
                "출처": section.source,
            }
        )

    st.dataframe(preview_rows, hide_index=True, use_container_width=True)
    if len(sections) > len(preview_rows):
        st.caption(f"화면에는 처음 {len(preview_rows)}개 항목만 표시했습니다.")


def render_table_micro_index(tables: list[ExtractedTable]) -> None:
    summary_rows = []
    for table in tables:
        row_count, column_count = table_dimensions(table)
        summary_rows.append(
            {
                "ID": f"Table {table.index}",
                "크기": f"{row_count}행 x {column_count}열",
                "식별 단서": table_fingerprint(table),
            }
        )

    st.dataframe(summary_rows, hide_index=True, use_container_width=True)


def render_table_preview(table: ExtractedTable) -> None:
    row_count, column_count = table_dimensions(table)
    st.caption(
        f"{table.source} · 전체 {row_count}행 x {column_count}열 · "
        "화면 미리보기는 성능을 위해 일부 행과 열만 표시합니다."
    )
    st.dataframe(
        rows_to_preview_records_limited(table.rows),
        hide_index=True,
        use_container_width=True,
    )


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
    uploaded_file_key = f"{uploaded_file.name}:{uploaded_file.size}"
    st.caption(f"{uploaded_file.name} · {uploaded_file.size:,} bytes")
    if st.session_state.get("uploaded_file_key") not in {None, uploaded_file_key}:
        st.session_state.pop("tables", None)
        st.session_state.pop("table_source", None)
        st.session_state.pop("table_pages", None)
        st.session_state.pop("pdf_sections", None)

    sections = st.session_state.get("pdf_sections")
    if sections is None:
        suffix = Path(uploaded_file.name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name

        try:
            with st.spinner("PDF 목차를 먼저 파악하는 중입니다..."):
                sections = extract_pdf_sections(tmp_path)
            st.session_state["pdf_sections"] = sections
            st.session_state["uploaded_file_key"] = uploaded_file_key
        except Exception as exc:
            sections = []
            st.session_state["pdf_sections"] = sections
            st.session_state["uploaded_file_key"] = uploaded_file_key
            st.warning(f"PDF 목차를 읽지 못했습니다. 페이지 직접 입력으로 진행해 주세요.\n\n상세: {exc}")
        finally:
            os.unlink(tmp_path)

    if sections:
        st.subheader("목차")
        st.caption(
            f"{sections[0].source} 기반으로 항목을 만들었습니다. "
            "필요한 항목만 선택하면 해당 페이지 범위만 분석합니다."
        )
        render_section_index(sections)

    with st.form("parse-options"):
        selected_sections: list[str] = []
        section_lookup: dict[str, PdfSection] = {}

        if sections:
            section_lookup = {section_option_label(section): section for section in sections}
            selected_sections = st.multiselect(
                "분석할 목차 항목",
                options=list(section_lookup.keys()),
                default=[],
                placeholder="테이블을 찾을 항목만 선택하세요.",
                help="선택한 항목의 페이지 범위를 합쳐서 테이블 파서에 전달합니다.",
            )

        pages = st.text_input(
            "페이지 직접 입력",
            placeholder="예: 1,3,5-7",
            help="목차 항목이 없거나 범위를 더 좁히고 싶을 때 사용하세요. 입력하면 목차 선택보다 우선합니다.",
        )
        submitted = st.form_submit_button("분석 시작", type="primary")

    if submitted:
        selected_section_objects = [
            section_lookup[label]
            for label in selected_sections
            if label in section_lookup
        ]
        manual_pages = pages.strip()
        if manual_pages:
            selected_pages = compact_page_numbers(parse_page_numbers(manual_pages))
            if not selected_pages:
                st.warning("페이지 직접 입력은 `1,3,5-7` 같은 숫자와 범위 형식으로 입력해 주세요.")
                st.stop()
        else:
            selected_pages = pages_from_sections(selected_section_objects)

        if not selected_pages:
            st.warning("분석할 목차 항목을 선택하거나 페이지 범위를 입력해 주세요.")
            st.stop()

        suffix = Path(uploaded_file.name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name

        try:
            with st.spinner("지정한 페이지에서 테이블을 찾는 중입니다..."):
                tables = parse_pdf_tables(tmp_path, pages=selected_pages)

            st.session_state["tables"] = tables
            st.session_state["table_source"] = uploaded_file.name
            st.session_state["table_pages"] = selected_pages

        except Exception as exc:
            st.session_state.pop("tables", None)
            st.error(f"PDF 파싱에 실패했습니다. 파일 형식 또는 내용 확인 후 다시 시도해 주세요.\n\n상세: {exc}")
        finally:
            os.unlink(tmp_path)

    tables = st.session_state.get("tables")
    if tables is not None:
        st.subheader("Tables")
        st.caption(
            f"{st.session_state.get('table_source', uploaded_file.name)} · "
            f"페이지: {st.session_state.get('table_pages', '전체')}"
        )

        if not tables:
            st.warning("선택한 페이지에서 추출 가능한 테이블을 찾지 못했습니다.")
        else:
            st.metric("발견된 테이블", len(tables))
            render_table_micro_index(tables)

            table_lookup = {table_option_label(table): table for table in tables}
            detail_label = st.selectbox(
                "상세 미리보기",
                options=["미리보기 없음"] + list(table_lookup.keys()),
                help="한 번에 하나만 열어 화면 렌더링 부담을 줄입니다.",
            )
            if detail_label != "미리보기 없음":
                detail_table = table_lookup[detail_label]
                render_table_preview(detail_table)

            selected_labels = st.multiselect(
                "내보낼 테이블",
                options=list(table_lookup.keys()),
                default=[],
                placeholder="내보낼 테이블만 선택하세요.",
            )
            selected_tables = [table_lookup[label] for label in selected_labels]

            output_format = st.radio(
                "내보내기 형식",
                options=["HTML", "Markdown"],
                horizontal=True,
            )

            if not selected_tables:
                st.info("선택한 테이블만 export 대상이 됩니다. 기본값은 비워 두어 화면 렌더링을 가볍게 유지합니다.")
            else:
                combined_output = combine_tables(selected_tables, output_format)
                extension = "html" if output_format == "HTML" else "md"
                mime_type = "text/html" if output_format == "HTML" else "text/markdown"
                st.download_button(
                    f"선택한 {len(selected_tables)}개 테이블 내보내기",
                    data=combined_output,
                    file_name=f"selected-tables.{extension}",
                    mime=mime_type,
                    type="primary",
                )
