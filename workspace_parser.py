#!/usr/bin/env python3
"""Парсер тендеров с workspace.ru через RSS-ленту."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import feedparser

RSS_URL = "https://workspace.ru/tenders/rss/"

# Порядок важен: apps проверяется раньше web, чтобы "разработка мобильного
# приложения" классифицировалась как apps, а не как web по слову "разработка".
CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("apps-development", ("мобильн", "приложен")),
    ("crm",              ("crm", "erp")),
    ("web-development",  ("сайт", "разработка")),
]
CATEGORIES = [slug for slug, _ in CATEGORY_KEYWORDS]

DATE_DMY_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
FIELD_RE = re.compile(r"<b>\s*([^<]+?)\s*</b>\s*:\s*([^<]*)", re.I)
BUDGET_IN_TITLE_RE = re.compile(r"Бюджет:\s*(.+?)$", re.I)
NUM_RE = re.compile(r"\d[\d\s ]*")


@dataclass
class Tender:
    title: str
    organizer: str
    budget_min: Optional[int]
    budget_max: Optional[int]
    budget_text: str
    deadline: str
    url: str
    published_date: str
    category: str
    service: str


def parse_description_fields(summary: str) -> dict[str, str]:
    """Вытаскивает пары <b>Лейбл</b>: значение из HTML description RSS."""
    fields: dict[str, str] = {}
    for label, value in FIELD_RE.findall(summary or ""):
        fields[label.strip().lower().rstrip(":")] = value.strip()
    return fields


def parse_dmy(s: str) -> str:
    """'23.04.2026' → '2026-04-23'. '' если не распознано."""
    m = DATE_DMY_RE.search(s or "")
    if not m:
        return ""
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def parse_budget_from_title(title: str) -> tuple[Optional[int], Optional[int], str]:
    """'... Бюджет: от 100 000 до 400 000 руб' → (100000, 400000, 'от 100 000 до 400 000 руб')."""
    m = BUDGET_IN_TITLE_RE.search(title or "")
    if not m:
        return None, None, ""
    raw = m.group(1).strip()
    nums = [int(re.sub(r"\s", "", n)) for n in NUM_RE.findall(raw)]
    if not nums:
        return None, None, raw
    if len(nums) == 1:
        return nums[0], nums[0], raw
    return nums[0], nums[-1], raw


def classify(service: str) -> Optional[str]:
    """Определяет slug категории по 'Требуемая услуга'. None = не подходит."""
    s = (service or "").lower()
    for slug, keywords in CATEGORY_KEYWORDS:
        if any(k in s for k in keywords):
            return slug
    return None


def entry_to_tender(entry) -> Optional[Tender]:
    summary = entry.get("summary", "")
    fields = parse_description_fields(summary)

    service = fields.get("требуемая услуга") or fields.get("требуемые услуги") or ""
    category = classify(service)
    if category is None:
        return None

    organizer = fields.get("организатор", "")
    deadline = parse_dmy(fields.get("крайний срок приема заявок", ""))
    published_iso = parse_dmy(fields.get("дата публикации", ""))
    if not published_iso:
        pp = getattr(entry, "published_parsed", None)
        if pp:
            published_iso = f"{pp.tm_year}-{pp.tm_mon:02d}-{pp.tm_mday:02d}"

    raw_title = entry.get("title", "")
    bmin, bmax, btext = parse_budget_from_title(raw_title)
    clean_title = re.sub(r"\.\s*Бюджет:.*$", "", raw_title).strip()

    return Tender(
        title=clean_title,
        organizer=organizer,
        budget_min=bmin,
        budget_max=bmax,
        budget_text=btext,
        deadline=deadline,
        url=entry.get("link", ""),
        published_date=published_iso,
        category=category,
        service=service,
    )


def main() -> int:
    default_cutoff = (date.today() - timedelta(days=2)).isoformat()
    ap = argparse.ArgumentParser(description="Workspace.ru tender parser (RSS)")
    ap.add_argument(
        "--cutoff-date",
        default=default_cutoff,
        help=f"Нижняя граница даты публикации (YYYY-MM-DD). По умолчанию {default_cutoff} (2 дня назад).",
    )
    ap.add_argument(
        "--sheets",
        action="store_true",
        help="Дозаписать в Google Sheets (env GOOGLE_CREDENTIALS_JSON, GOOGLE_SHEET_ID).",
    )
    args = ap.parse_args()

    print(f"=== RSS: {RSS_URL} ===")
    feed = feedparser.parse(RSS_URL)
    if feed.bozo:
        print(f"RSS warning: {feed.bozo_exception}", file=sys.stderr)
    print(f"Всего entries: {len(feed.entries)}")

    tenders: list[Tender] = []
    seen_urls: set[str] = set()
    skipped_category = 0
    for entry in feed.entries:
        t = entry_to_tender(entry)
        if t is None:
            skipped_category += 1
            continue
        if t.url and t.url in seen_urls:
            continue
        seen_urls.add(t.url)
        tenders.append(t)
    print(f"Отсеяно по категории (ни одно из: разработка/сайт/мобильн/приложен/CRM/ERP): {skipped_category}")
    print(f"Подходящих по категории: {len(tenders)}")

    before = len(tenders)
    tenders = [
        t for t in tenders
        if t.published_date and t.published_date >= args.cutoff_date
    ]
    print(f"После фильтра по дате ≥ {args.cutoff_date}: {len(tenders)} (было {before})")

    print(f"\nИтого: {len(tenders)}")
    for t in tenders:
        print(f"  [{t.published_date}] [{t.category}] {t.title}")
        print(f"     бюджет: {t.budget_text or '—'} | дедлайн: {t.deadline or '—'} | орг: {t.organizer or '—'}")
        print(f"     услуга: {t.service}")
        print(f"     {t.url}")

    if args.sheets:
        import sheets_writer

        added = sheets_writer.write_tenders(tenders)
        print(f"Google Sheets: добавлено {added} из {len(tenders)} (остальное — дубли по ссылке)")

    counts = {slug: 0 for slug in CATEGORIES}
    for t in tenders:
        if t.category in counts:
            counts[t.category] += 1
    print(f"COUNTS_JSON={json.dumps(counts, ensure_ascii=False)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
