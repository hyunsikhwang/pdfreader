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
    section_path: list[str]


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


def detect_section_level(line: str) -> int | None:
    text = normalize_text(line.strip().lstrip("#").strip())
    if not text:
        return None

    if re.match(r"^\d+\.\s+\S", text):
        return 1
    if re.match(r"^\d+-\d+\.\s+\S", text):
        return 2
    if re.match(r"^\d+\)\s+\S", text):
        return 3
    if re.match(r"^\[[^\]]+\]", text):
        return 4
    if re.match(r"^\(\d+\)\s+\S", text):
        return 5
    if line.lstrip().startswith("#"):
        return min(len(line) - len(line.lstrip("#")), 6)

    return None


def update_section_path(path: list[tuple[int, str]], line: str) -> list[tuple[int, str]]:
    level = detect_section_level(line)
    if level is None:
        return path

    title = normalize_text(line.strip().lstrip("#").strip())
    if not title:
        return path

    return [(path_level, text) for path_level, text in path if path_level < level] + [(level, title)]


def build_table_from_markdown(
    markdown_table: str,
    source: str,
    section_path: list[str],
    index: int,
) -> ExtractedTable | None:
    rows = markdown_table_to_rows(markdown_table)
    if not rows:
        return None

    return ExtractedTable(
        index=index,
        source=source,
        html=rows_to_html(rows),
        markdown=rows_to_markdown(rows),
        rows=rows,
        section_path=section_path,
    )


def extract_markdown_tables_with_context(markdown_text: str, source: str) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    current_path: list[tuple[int, str]] = []
    current_block: list[str] = []
    current_block_path: list[str] = []

    def flush_table_block() -> None:
        nonlocal current_block, current_block_path
        if len(current_block) < 2:
            current_block = []
            current_block_path = []
            return

        table = build_table_from_markdown(
            "\n".join(current_block),
            source=source,
            section_path=current_block_path,
            index=len(tables) + 1,
        )
        if table is not None:
            tables.append(table)

        current_block = []
        current_block_path = []

    for line in markdown_text.splitlines():
        if "|" in line.strip():
            if not current_block:
                current_block_path = [text for _, text in current_path]
            current_block.append(line.rstrip())
            continue

        flush_table_block()
        current_path = update_section_path(current_path, line)

    flush_table_block()
    return tables


def parse_pdf_tables(input_path: str) -> list[ExtractedTable]:
    with tempfile.TemporaryDirectory() as output_dir:
        opendataloader_pdf.convert(
            input_path=input_path,
            output_dir=output_dir,
            format=["html", "markdown"],
            quiet=True,
        )

        tables: list[ExtractedTable] = []
        markdown_files = sorted(Path(output_dir).glob("*.md"))
        markdown_files.extend(sorted(Path(output_dir).glob("*.markdown")))

        for markdown_file in markdown_files:
            markdown_text = markdown_file.read_text(encoding="utf-8")
            for table in extract_markdown_tables_with_context(markdown_text, markdown_file.name):
                table.index = len(tables) + 1
                tables.append(table)

        if tables:
            return tables

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
                        section_path=[],
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


def table_search_text(table: ExtractedTable) -> str:
    return normalize_text(" ".join(cell for row in table.rows for cell in row)).casefold()


def table_section_text(table: ExtractedTable) -> str:
    return " > ".join(getattr(table, "section_path", []))


def tokenize_table_query(query: str) -> list[str]:
    tokens = re.findall(r'"([^"]+)"|(\S+)', query)
    return [quoted or plain for quoted, plain in tokens]


def is_section_path_query(query: str) -> bool:
    return ">>" in query or "\n" in query


def parse_section_path_query(query: str) -> list[str]:
    parts: list[str] = []
    for line in query.replace(">>", "\n").splitlines():
        text = normalize_text(line.strip().lstrip(">").strip())
        if text:
            parts.append(text.casefold())

    return parts


def normalize_section_match_text(value: str) -> str:
    text = normalize_text(value).casefold()
    text = re.sub(r"^[\[\(\{<\s]*\d+(?:[-.]\d+)*[.)]?\s*", "", text)
    text = re.sub(r"^[\[\(\{<\s]*", "", text)
    text = re.sub(r"[\]\)\}>]\s*$", "", text)
    text = re.sub(r"[\s\[\]\(\)\{\}<>:：,，.;；·ㆍ-]+", "", text)
    return text


def section_part_matches(query_part: str, path_part: str) -> bool:
    normalized_query = normalize_section_match_text(query_part)
    normalized_path = normalize_section_match_text(path_part)
    if not normalized_query:
        return True

    return normalized_query in normalized_path


def table_matches_section_path(table: ExtractedTable, query: str) -> bool:
    query_parts = parse_section_path_query(query)
    if not query_parts:
        return True

    search_start = 0

    for query_part in query_parts:
        matched_index = None
        section_path = getattr(table, "section_path", [])
        for path_index in range(search_start, len(section_path)):
            if section_part_matches(query_part, section_path[path_index]):
                matched_index = path_index
                break

        if matched_index is None:
            return False

        search_start = matched_index + 1

    return True


def diagnose_section_path_match(table: ExtractedTable, query: str) -> dict[str, object]:
    query_parts = parse_section_path_query(query)
    steps: list[dict[str, object]] = []
    search_start = 0
    section_path = getattr(table, "section_path", [])

    for step_index, query_part in enumerate(query_parts, start=1):
        matched_index = None
        normalized_query = normalize_section_match_text(query_part)

        for path_index in range(search_start, len(section_path)):
            if section_part_matches(query_part, section_path[path_index]):
                matched_index = path_index
                break

        if matched_index is None:
            steps.append(
                {
                    "단계": step_index,
                    "검색 항목": query_part,
                    "정규화 검색어": normalized_query,
                    "상태": "실패",
                    "매칭된 문서 항목": "",
                    "검색 시작 위치": search_start + 1,
                }
            )
            return {
                "table": table,
                "matched": False,
                "matched_steps": step_index - 1,
                "total_steps": len(query_parts),
                "failed_step": step_index,
                "steps": steps,
            }

        matched_path = section_path[matched_index]
        steps.append(
            {
                "단계": step_index,
                "검색 항목": query_part,
                "정규화 검색어": normalized_query,
                "상태": "성공",
                "매칭된 문서 항목": matched_path,
                "검색 시작 위치": search_start + 1,
            }
        )
        search_start = matched_index + 1

    return {
        "table": table,
        "matched": True,
        "matched_steps": len(query_parts),
        "total_steps": len(query_parts),
        "failed_step": None,
        "steps": steps,
    }


def render_section_path_diagnostics(tables: list[ExtractedTable], query: str) -> None:
    if not is_section_path_query(query):
        return

    diagnostics = [diagnose_section_path_match(table, query) for table in tables]
    matched_count = sum(1 for diagnostic in diagnostics if diagnostic["matched"])
    summary_rows = []

    for diagnostic in diagnostics:
        table = diagnostic["table"]
        failed_step = diagnostic["failed_step"]
        summary_rows.append(
            {
                "ID": f"Table {getattr(table, 'index', '-')}",
                "결과": "성공" if diagnostic["matched"] else f"{failed_step}단계 실패",
                "진행": f"{diagnostic['matched_steps']} / {diagnostic['total_steps']}",
                "항목 경로": shorten_text(table_section_text(table), 220) if getattr(table, "section_path", []) else "-",
                "식별 단서": table_fingerprint(table),
            }
        )

    with st.expander(f"항목 경로 검색 진단 · {matched_count}/{len(tables)}개 성공", expanded=matched_count == 0):
        st.dataframe(summary_rows, hide_index=True, use_container_width=True)

        table_labels = {}
        for diagnostic in diagnostics:
            table = diagnostic["table"]
            result_label = "성공" if diagnostic["matched"] else f"{diagnostic['failed_step']}단계 실패"
            table_labels[f"Table {getattr(table, 'index', '-')} · {result_label}"] = diagnostic
        selected_label = st.selectbox(
            "단계별 상세",
            options=list(table_labels.keys()),
            key="section-path-diagnostic-detail",
        )
        selected_diagnostic = table_labels[selected_label]
        st.dataframe(selected_diagnostic["steps"], hide_index=True, use_container_width=True)


def table_matches_query(table: ExtractedTable, query: str) -> bool:
    tokens = tokenize_table_query(query)
    if not tokens:
        return True

    text = table_search_text(table)
    groups: list[list[tuple[str, bool]]] = [[]]
    negate_next = False

    for token in tokens:
        upper_token = token.upper()
        if upper_token == "OR":
            if groups[-1]:
                groups.append([])
            negate_next = False
            continue

        if upper_token == "AND":
            continue

        if upper_token == "NOT":
            negate_next = True
            continue

        groups[-1].append((token.casefold(), negate_next))
        negate_next = False

    for group in groups:
        if not group:
            continue

        if all((term not in text) if negated else (term in text) for term, negated in group):
            return True

    return False


def filter_tables_by_query(tables: list[ExtractedTable], query: str) -> list[ExtractedTable]:
    cleaned_query = query.strip()
    if not cleaned_query:
        return tables

    if is_section_path_query(cleaned_query):
        return [table for table in tables if table_matches_section_path(table, cleaned_query)]

    return [table for table in tables if table_matches_query(table, cleaned_query)]


def render_table_micro_index(tables: list[ExtractedTable]) -> None:
    summary_rows = []
    for table in tables:
        row_count, column_count = table_dimensions(table)
        summary_rows.append(
            {
                "ID": f"Table {table.index}",
                "크기": f"{row_count}행 x {column_count}열",
                "항목 경로": shorten_text(table_section_text(table), 160) if getattr(table, "section_path", []) else "-",
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
    if getattr(table, "section_path", []):
        st.caption(table_section_text(table))
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
        section_text = table_section_text(table)
        if output_format == "HTML":
            section_heading = f"<p><strong>{escape(section_text)}</strong></p>\n" if section_text else ""
            sections.append(f"<h2>{escape(title)}</h2>\n{section_heading}{table.html}")
        else:
            section_heading = f"\n\n{section_text}" if section_text else ""
            sections.append(f"## {title}{section_heading}\n\n{table.markdown}")

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
        st.session_state.pop("filtered_tables", None)
        st.session_state.pop("table_query", None)
        st.session_state.pop("table_source", None)
        st.session_state["uploaded_file_key"] = uploaded_file_key

    with st.form("table-search"):
        table_query = st.text_area(
            "테이블 내용 또는 항목 경로 조건",
            placeholder=(
                '예: 매출 AND 영업이익\n\n'
                '또는\n'
                '5. 경영지표\n'
                '>> 5-2. 지급여력비율\n'
                '>> 2) 지급여력비율의 경과조치 적용에 관한 세부사항'
            ),
            help=(
                "한 줄 조건은 테이블 내용에서 검색합니다. 여러 줄 또는 >> 조건은 테이블이 속한 문서 항목 경로에서 검색합니다. "
                "조건을 비워두면 모든 테이블을 가져옵니다."
            ),
            height=140,
        )
        submitted = st.form_submit_button("테이블 검색", type="primary")

    if submitted:
        suffix = Path(uploaded_file.name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name

        try:
            with st.spinner("PDF 전체에서 테이블을 추출하고 조건을 적용하는 중입니다..."):
                tables = parse_pdf_tables(tmp_path)
                filtered_tables = filter_tables_by_query(tables, table_query)

            st.session_state["tables"] = tables
            st.session_state["filtered_tables"] = filtered_tables
            st.session_state["table_query"] = table_query.strip()
            st.session_state["table_source"] = uploaded_file.name
            st.session_state["uploaded_file_key"] = uploaded_file_key

        except Exception as exc:
            st.session_state.pop("tables", None)
            st.session_state.pop("filtered_tables", None)
            st.error(f"PDF 파싱에 실패했습니다. 파일 형식 또는 내용 확인 후 다시 시도해 주세요.\n\n상세: {exc}")
        finally:
            os.unlink(tmp_path)

    tables = st.session_state.get("tables")
    filtered_tables = st.session_state.get("filtered_tables")
    if tables is not None and filtered_tables is not None:
        st.subheader("Tables")
        st.caption(st.session_state.get("table_source", uploaded_file.name))

        if not tables:
            st.warning("업로드한 PDF에서 추출 가능한 테이블을 찾지 못했습니다.")
        else:
            metric_columns = st.columns(2)
            metric_columns[0].metric("전체 테이블", len(tables))
            metric_columns[1].metric("조건 일치", len(filtered_tables))

            active_query = st.session_state.get("table_query", "")
            if active_query:
                st.caption(f"적용 조건: `{active_query}`")
            else:
                st.caption("조건 없이 모든 테이블을 표시합니다.")

            render_section_path_diagnostics(tables, active_query)

            if not filtered_tables:
                st.warning("조건에 맞는 테이블이 없습니다. 검색어 또는 논리 조건을 조정해 주세요.")
                st.stop()

            render_table_micro_index(filtered_tables)

            table_lookup = {table_option_label(table): table for table in filtered_tables}
            detail_label = st.selectbox(
                "상세 미리보기",
                options=["미리보기 없음"] + list(table_lookup.keys()),
                help="한 번에 하나만 열어 화면 렌더링 부담을 줄입니다.",
            )
            if detail_label != "미리보기 없음":
                detail_table = table_lookup[detail_label]
                render_table_preview(detail_table)

            export_all_filtered = st.checkbox(
                "조건에 맞는 테이블 전체를 export 대상으로 사용",
                value=False,
            )
            if export_all_filtered:
                selected_tables = filtered_tables
            else:
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
                st.info("선택한 테이블만 export 대상이 됩니다. 조건 필터로 좁힌 뒤 필요한 테이블만 고르세요.")
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
