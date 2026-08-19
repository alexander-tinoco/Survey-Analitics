"""Tests for reading uploaded export files.

The parser is pure, so every case here is a literal in this file — no
database, no fixtures on disk.
"""

import io

import pandas as pd
import pytest

from apps.surveys.services.parsing import MAX_COLUMNS, ParseError, parse_upload


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


class TestCsvReading:
    def test_reads_a_comma_separated_export(self) -> None:
        parsed = parse_upload(csv_bytes("Age,City\n34,Lima\n29,Quito\n"), "survey.csv")

        assert parsed.respondent_count == 2
        assert parsed.question_count == 2
        assert list(parsed.frame.columns) == ["Age", "City"]

    def test_reads_a_semicolon_separated_export(self) -> None:
        """Localized spreadsheet software exports with semicolons.

        Assuming a comma would yield one giant column, and every question
        after the first would silently disappear.
        """
        parsed = parse_upload(csv_bytes("Age;City\n34;Lima\n29;Quito\n"), "survey.csv")

        assert parsed.question_count == 2
        assert list(parsed.frame.columns) == ["Age", "City"]

    def test_reads_a_tab_separated_export(self) -> None:
        parsed = parse_upload(csv_bytes("Age\tCity\n34\tLima\n"), "survey.csv")

        assert parsed.question_count == 2

    def test_reads_latin_1_when_utf_8_fails(self) -> None:
        """Older exports are not always UTF-8, and rejecting them is unhelpful."""
        content = "Ciudad\nBogotá\n".encode("latin-1")

        parsed = parse_upload(content, "survey.csv")

        assert parsed.respondent_count == 1

    def test_strips_a_utf_8_byte_order_mark(self) -> None:
        """Excel writes a BOM; unhandled, it becomes part of the first header."""
        parsed = parse_upload("﻿Age,City\n34,Lima\n".encode(), "survey.csv")

        assert list(parsed.frame.columns) == ["Age", "City"]

    def test_trims_whitespace_around_headers(self) -> None:
        parsed = parse_upload(csv_bytes("  Age ,City\n34,Lima\n"), "survey.csv")

        assert list(parsed.frame.columns) == ["Age", "City"]


class TestCleaning:
    def test_drops_fully_empty_columns(self) -> None:
        """Spreadsheet exports routinely carry blank trailing columns."""
        parsed = parse_upload(csv_bytes("Age,Empty,City\n34,,Lima\n29,,Quito\n"), "s.csv")

        assert list(parsed.frame.columns) == ["Age", "City"]

    def test_drops_fully_empty_rows(self) -> None:
        parsed = parse_upload(csv_bytes("Age,City\n34,Lima\n,\n29,Quito\n"), "s.csv")

        assert parsed.respondent_count == 2

    def test_drops_the_unnamed_index_column(self) -> None:
        """A frame saved with its index reappears as 'Unnamed: 0'."""
        parsed = parse_upload(csv_bytes(",Age,City\n0,34,Lima\n"), "s.csv")

        assert list(parsed.frame.columns) == ["Age", "City"]


class TestRejection:
    def test_empty_content_is_rejected(self) -> None:
        with pytest.raises(ParseError, match="empty"):
            parse_upload(b"", "survey.csv")

    def test_unsupported_extension_is_rejected(self) -> None:
        with pytest.raises(ParseError, match="Only .csv"):
            parse_upload(csv_bytes("Age\n34\n"), "survey.pdf")

    def test_header_only_file_is_rejected(self) -> None:
        with pytest.raises(ParseError, match="no data rows"):
            parse_upload(csv_bytes("Age,City\n"), "survey.csv")

    def test_duplicate_headers_are_rejected(self) -> None:
        """Two questions with one title makes every later result ambiguous.

        pandas disambiguates them to "Age" and "Age.1" before we see the
        frame, so the file must be refused rather than silently accepted with
        a question the user never wrote.
        """
        with pytest.raises(ParseError, match="appears more than once"):
            parse_upload(csv_bytes("Age,Age\n34,35\n"), "survey.csv")

    def test_a_legitimate_dotted_header_is_not_mistaken_for_a_duplicate(self) -> None:
        """ "Q1.1" only looks like a rename when "Q1" is also present."""
        parsed = parse_upload(csv_bytes("Q1.1,Q2\n34,35\n"), "survey.csv")

        assert list(parsed.frame.columns) == ["Q1.1", "Q2"]

    def test_too_many_columns_is_rejected(self) -> None:
        headers = ",".join(f"q{i}" for i in range(MAX_COLUMNS + 1))
        values = ",".join("1" for _ in range(MAX_COLUMNS + 1))

        with pytest.raises(ParseError, match="more than"):
            parse_upload(csv_bytes(f"{headers}\n{values}\n"), "survey.csv")

    def test_ragged_rows_are_reported_in_plain_language(self) -> None:
        """The message must help the uploader, who can fix a stray quote."""
        content = csv_bytes('Age,City\n34,"Lima\n29,Quito,extra,more\n')

        with pytest.raises(ParseError, match="consistent number of columns"):
            parse_upload(content, "survey.csv")


class TestExcelReading:
    def test_reads_the_first_sheet_of_a_workbook(self) -> None:
        buffer = io.BytesIO()
        pd.DataFrame({"Age": [34, 29], "City": ["Lima", "Quito"]}).to_excel(buffer, index=False)

        parsed = parse_upload(buffer.getvalue(), "survey.xlsx")

        assert parsed.respondent_count == 2
        assert list(parsed.frame.columns) == ["Age", "City"]

    def test_a_file_that_is_not_a_workbook_is_rejected(self) -> None:
        with pytest.raises(ParseError, match="could not be read as a spreadsheet"):
            parse_upload(b"this is not a workbook", "survey.xlsx")
