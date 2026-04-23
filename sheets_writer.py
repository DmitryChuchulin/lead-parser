"""Дозапись тендеров в Google Sheets (append, без перезаписи)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import gspread
from google.oauth2.service_account import Credentials

if TYPE_CHECKING:
    from workspace_parser import Tender

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_WORKSHEET_NAME = "workspace"
DEFAULT_HEADERS = [
    "Название", "Организатор", "Бюджет", "Дедлайн",
    "Ссылка", "Площадка", "Дата публикации",
]
PLATFORM = "workspace.ru"


def _load_credentials() -> Credentials:
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        raise RuntimeError("переменная окружения GOOGLE_CREDENTIALS_JSON не задана")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise RuntimeError(
                f"GOOGLE_CREDENTIALS_JSON не валидный JSON и не существующий файл: {raw!r}"
            ) from None
        info = json.loads(path.read_text(encoding="utf-8"))
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def _get_worksheet(client: gspread.Client, sheet_id: str,
                   worksheet_name: str, headers: list[str]) -> gspread.Worksheet:
    spreadsheet = client.open_by_key(sheet_id)
    try:
        ws = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(headers))
    first_row = ws.row_values(1)
    if first_row != headers:
        if first_row:
            ws.insert_row(headers, index=1, value_input_option="USER_ENTERED")
        else:
            ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


def write_tenders(tenders: Sequence, *, worksheet_name: str = DEFAULT_WORKSHEET_NAME,
                  headers: list[str] = DEFAULT_HEADERS) -> int:
    """Дозаписывает тендеры, пропуская URL'ы, которые уже есть в колонке E.

    Возвращает количество добавленных строк.
    """
    if not tenders:
        return 0
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("переменная окружения GOOGLE_SHEET_ID не задана")
    client = gspread.authorize(_load_credentials())
    ws = _get_worksheet(client, sheet_id, worksheet_name, headers)

    existing_urls = set(ws.col_values(5)[1:])  # колонка E = "Ссылка", пропускаем заголовок
    fresh = [t for t in tenders if t.url not in existing_urls]
    if not fresh:
        return 0

    rows = [
        [t.title, t.organizer, t.budget_text, t.deadline,
         t.url, PLATFORM, t.published_date]
        for t in fresh
    ]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    return len(rows)
