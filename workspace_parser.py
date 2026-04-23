#!/usr/bin/env python3
"""Парсер тендеров с workspace.ru по категориям."""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://workspace.ru"
CATEGORIES = {
    "web-development": "Разработка сайтов",
    "apps-development": "Мобильные приложения",
    "crm": "CRM / ПО / чат-боты",
}
PAGES_PER_CATEGORY = 2
TIMEOUT = 20
MIN_DELAY = 1.0
MAX_DELAY = 2.5
MIN_BUDGET = 300_000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

DATE_RE = re.compile(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", re.I)
NUM_RE = re.compile(r"\d[\d\s ]*")


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


def fetch(session: requests.Session, url: str) -> Optional[str]:
    try:
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        print(f"    ошибка запроса {url}: {exc}", file=sys.stderr)
        return None
    if resp.status_code != 200:
        print(f"    HTTP {resp.status_code} {url}", file=sys.stderr)
        return None
    return resp.text


def parse_ru_date(text: str) -> str:
    """'23 апреля 2026' → '2026-04-23'. Возвращает '' если не распознано."""
    m = DATE_RE.search(text or "")
    if not m:
        return ""
    day, month_word, year = m.group(1), m.group(2).lower(), m.group(3)
    month = RU_MONTHS.get(month_word)
    if not month:
        return ""
    return f"{year}-{month:02d}-{int(day):02d}"


def parse_budget(text: str) -> tuple[Optional[int], Optional[int], str]:
    """'100 000 - 400 000' → (100000, 400000, '100 000 - 400 000 руб')."""
    text = (text or "").strip()
    if not text:
        return None, None, ""
    nums = [int(re.sub(r"\s", "", n)) for n in NUM_RE.findall(text)]
    if not nums:
        return None, None, text
    display = f"{text} руб" if "руб" not in text.lower() else text
    if len(nums) == 1:
        return nums[0], nums[0], display
    return nums[0], nums[-1], display


def parse_card(card, category: str) -> Optional[Tender]:
    title_a = card.select_one("div.b-tender__title a[href]")
    if not title_a:
        return None
    url = urljoin(BASE_URL, title_a["href"])
    title = title_a.get_text(strip=True)

    budget_el = card.select_one(
        "div.b-tender__block--title .b-tender__info-item-text"
    )
    budget_raw = ""
    if budget_el:
        budget_raw = re.sub(r"\s+", " ", budget_el.get_text(" ", strip=True)).strip()
    b_min, b_max, budget_text = parse_budget(budget_raw)

    published_iso = ""
    deadline_iso = ""
    for item in card.select("div.b-tender__info-item"):
        title_el = item.select_one(".b-tender__info-item-title")
        text_el = item.select_one(".b-tender__info-item-text")
        if not title_el or not text_el:
            continue
        label = title_el.get_text(strip=True).lower().rstrip(":")
        value_text = text_el.get_text(" ", strip=True)
        if label.startswith("опубликован"):
            published_iso = parse_ru_date(value_text)
        elif "срок" in label or "заявок" in label:
            deadline_iso = parse_ru_date(value_text)

    return Tender(
        title=title,
        organizer="",
        budget_min=b_min,
        budget_max=b_max,
        budget_text=budget_text,
        deadline=deadline_iso,
        url=url,
        published_date=published_iso,
        category=category,
    )


def collect_category(session: requests.Session, slug: str, pages: int) -> list[Tender]:
    tenders: list[Tender] = []
    for page in range(1, pages + 1):
        url = f"{BASE_URL}/tenders/{slug}/?SORT=public&ORDER=0&page={page}"
        print(f"  [{slug} p{page}] {url}")
        html = fetch(session, url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("div.vacancies__card._tender")
            parsed = [t for t in (parse_card(c, slug) for c in cards) if t]
            print(f"    карточек: {len(cards)}, распарсено: {len(parsed)}")
            tenders.extend(parsed)
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    return tenders


def enrich_organizer(session: requests.Session, tenders: list[Tender]) -> list[Tender]:
    for i, t in enumerate(tenders, 1):
        html = fetch(session, t.url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for inner in soup.select("div.card-info__inner"):
                title_el = inner.select_one(".card-info__title")
                desc_el = inner.select_one(".card-info__desc")
                if not title_el or not desc_el:
                    continue
                # "Oрганизатор" в HTML приходит с латинской O — match по общему хвосту
                if "рганизатор" in title_el.get_text(strip=True):
                    t.organizer = desc_el.get_text(strip=True)
                    break
        print(f"  [{i}/{len(tenders)}] организатор='{t.organizer}'  {t.url}")
        if i < len(tenders):
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    return tenders


def filter_by_date(tenders: list[Tender], cutoff: str) -> list[Tender]:
    return [t for t in tenders if t.published_date and t.published_date >= cutoff]


def filter_by_budget(tenders: list[Tender], min_budget: int) -> list[Tender]:
    return [t for t in tenders if t.budget_min is None or t.budget_min >= min_budget]


def main() -> int:
    default_cutoff = (date.today() - timedelta(days=2)).isoformat()
    ap = argparse.ArgumentParser(description="Workspace.ru tender parser")
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

    session = requests.Session()

    print(f"=== Шаг 1: сбор карточек из {len(CATEGORIES)} категорий × {PAGES_PER_CATEGORY} стр. ===")
    all_tenders: list[Tender] = []
    for slug in CATEGORIES:
        all_tenders.extend(collect_category(session, slug, PAGES_PER_CATEGORY))
    print(f"Всего карточек: {len(all_tenders)}")

    seen: dict[str, Tender] = {}
    for t in all_tenders:
        seen.setdefault(t.url, t)
    tenders = list(seen.values())
    print(f"После дедупликации по URL: {len(tenders)}")

    before = len(tenders)
    tenders = filter_by_date(tenders, args.cutoff_date)
    print(f"После фильтра по дате ≥ {args.cutoff_date}: {len(tenders)} (было {before})")

    before = len(tenders)
    tenders = filter_by_budget(tenders, MIN_BUDGET)
    print(f"После фильтра по бюджету (min ≥ {MIN_BUDGET:,} ₽ либо бюджет не указан): {len(tenders)} (было {before})")

    if tenders:
        print(f"\n=== Шаг 2: обогащение организатором ({len(tenders)} тендеров) ===")
        enrich_organizer(session, tenders)

    print(f"\nИтого: {len(tenders)}")
    for t in tenders:
        print(f"  [{t.published_date}] {t.title} | {t.budget_text} | {t.organizer} | {t.url}")

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
