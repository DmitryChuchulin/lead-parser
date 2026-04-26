# Lead Parser

Ежедневный парсер коммерческих тендеров на IT-разработку.  
Цель — лидогенерация: найти тендер → оценить → подать заявку.

---

## Что делает

- Парсит тендеры с **workspace.ru** через RSS (`/tenders/rss/`)
- Фильтрует по категориям: разработка сайтов, мобильные приложения, CRM/ПО
- Фильтрует по дате (не старше 2 дней)
- Записывает в Google Sheets без дублей
- Шлёт детальное уведомление в Telegram с разбивкой по категориям

---

## Структура файлов

```
lead-parser/
├── workspace_parser.py    # Парсер тендеров workspace.ru
├── sheets_writer.py       # Запись в Google Sheets
├── run.sh                 # Shell-скрипт запуска с Telegram уведомлением
├── requirements.txt       # Зависимости Python
├── .env                   # Секреты (не в git)
└── .github/
    └── workflows/
        └── daily_parse.yml  # GitHub Actions (отключён — workspace.ru блокирует их IP)
```

---

## Почему не GitHub Actions

workspace.ru возвращает **HTTP 471** для запросов с IP GitHub Actions (блокировка облачных серверов). Поэтому парсер запускается с VPS на netangels, IP которого не заблокирован.

---

## Как работает workspace парсер

1. Делает один HTTP запрос к RSS `https://workspace.ru/tenders/rss/`
2. Получает последние 10 тендеров с полями: заголовок, ссылка, дата, описание
3. Из описания (HTML в CDATA) парсит: организатор, бюджет, дедлайн, требуемая услуга
4. Фильтрует по ключевым словам в поле "Требуемая услуга":
   - `apps-development`: мобильн, приложен
   - `crm`: crm, erp
   - `web-development`: сайт, разработка
5. Фильтрует по дате
6. Записывает в Google Sheets, шлёт Telegram уведомление

Прогон занимает ~5-10 секунд.

---

## Google Sheets

| Таблица | ID | Вкладка |
|---|---|---|
| Lead Parser | `1NE1KD9YQ2lzJGKN5-c7Z3Ug9PFAEF7-4yomsMww9aPI` | `Workspace` |

Колонки: `Название | Организатор | Бюджет | Дедлайн | Ссылка | Площадка | Дата публикации`

---

## Telegram уведомление (формат)

**Успех:**
```
✅ workspace.ru
🌐 Сайты: 2
📱 Мобилки: 0
⚙️ CRM: 1
```

**Ошибка:**
```
❌ workspace.ru: ошибка!
```

---

## Переменные окружения (.env)

```env
GOOGLE_SHEET_ID=1NE1KD9YQ2lzJGKN5-c7Z3Ug9PFAEF7-4yomsMww9aPI
GOOGLE_CREDENTIALS_JSON=/opt/service-account.json
TELEGRAM_BOT_TOKEN=<токен бота @ElgrowsBot>
TELEGRAM_CHAT_ID=<chat_id Дмитрия>
```

---

## Запуск вручную

```bash
# Через shell скрипт (с Telegram уведомлением)
/opt/lead-parser/run.sh

# Напрямую (без уведомления)
cd /opt/lead-parser
set -a && source .env && set +a
.venv/bin/python workspace_parser.py --sheets

# Тест без записи в Sheets
.venv/bin/python workspace_parser.py
```

---

## Расписание на сервере (cron)

Сервер: `213.189.220.225` (netangels VPS)

```
0 6  * * *   Workspace парсер   → 09:00 МСК
0 11 * * *   Workspace парсер   → 14:00 МСК
0 15 * * *   Workspace парсер   → 18:00 МСК
```

Посмотреть cron: `crontab -l`  
Редактировать: `crontab -e`

---

## Инфраструктура

- **Сервер:** netangels VPS, Debian 12, 8GB RAM
- **Python:** 3.11, venv в `/opt/lead-parser/.venv/`
- **Google:** Service Account `tenchat-parser@tenchat-parser.iam.gserviceaccount.com`
- **Credentials файл:** `/opt/service-account.json`
- **Telegram:** бот @ElgrowsBot

---

## Зависимости

```
requests>=2.31
beautifulsoup4>=4.12
feedparser>=6.0.0
gspread>=6.0.0
google-auth>=2.0.0
```

---

## Площадки в планах

- **bizdaar.com** — коммерческие тендеры (есть аккаунт, нужно найти API через DevTools после логина)
- tender.pro
- b2b-center.ru

**Не парсим:** госзакупки (44-ФЗ, 223-ФЗ) — отдельная история с КЭП и документацией.

---

## Известные ограничения

- RSS workspace.ru отдаёт только последние 10 тендеров
- Организатор в RSS = тип ("юридическое лицо"), не название компании — название скрыто до подачи заявки
