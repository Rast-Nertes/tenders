"""
b2b_parser.py

- GoogleSheetsClient: работа с gspread (open_by_key, ensure_headers, append_rows)
- TenderParserBase: абстрактный базовый класс парсера площадки
- B2BParser: конкретная реализация для b2b-center.ru (авторизация + сбор строк таблицы)
"""

from typing import List, Dict
import time
import random
import os

from settings import *
import gspread
from oauth2client.service_account import ServiceAccountCredentials

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# -------------------------------
# Google Sheets helper
# -------------------------------
class GoogleSheetsClient:
    def __init__(self, service_account_file: str, spreadsheet_key: str, sheet_index: int = 0):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(service_account_file, scope)
        self.client = gspread.authorize(creds)
        self.spreadsheet_key = spreadsheet_key
        self.sheet_index = sheet_index
        self.sheet = self._open_sheet_by_key(spreadsheet_key, sheet_index)

    def _open_sheet_by_key(self, key: str, index: int):
        spreadsheet = self.client.open_by_key(key)
        return spreadsheet.get_worksheet(index)

    def ensure_headers(self, headers: List[str]):
        try:
            first_row = self.sheet.row_values(1)
            if not first_row:
                self.sheet.append_row(headers)
        except Exception as e:
            print(f"[GoogleSheetsClient] Ошибка ensure_headers: {e}")

    def append_rows(self, rows: List[List[str]]):
        """
        Пакетная запись строк. gspread имеет .append_rows (в новых версиях).
        Если не доступно, падает на поэлементную запись.
        """
        if not rows:
            return
        try:
            # Используем пакетную вставку, если доступно
            self.sheet.append_rows(rows, value_input_option="USER_ENTERED")
        except Exception as e:
            print(f"[GoogleSheetsClient] append_rows failed ({e}), falling back to append_row loop")
            for r in rows:
                try:
                    self.sheet.append_row(r)
                except Exception as e2:
                    print(f"[GoogleSheetsClient] append_row failed: {e2}")


# -------------------------------
# Keywords loader
# -------------------------------
class KeywordLoader:
    @staticmethod
    def load(path: str) -> List[str]:
        if not os.path.exists(path):
            print(f"[KeywordLoader] Файл ключевых слов не найден: {path}")
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]


# -------------------------------
# Base parser class
# -------------------------------
class TenderParserBase:
    """
    Базовый класс. Для новой площадки унаследуй и реализуй:
      - _login()
      - _get_tender_rows()
      - _parse_row(row)
    """
    def __init__(self, keywords: List[str], gs_client: GoogleSheetsClient, headless: bool = False):
        self.keywords = keywords
        self.gs = gs_client
        self.driver = None
        self.headless = headless

    def _start_driver(self):
        # здесь можно расширять параметры (binary_location, args)
        options = {}
        # undetected_chromedriver сам берёт параметры через uc.Chrome()
        # version_main можно указывать при необходимости
        self.driver = uc.Chrome(version_main=139)
        self.driver.maximize_window()
        return self.driver

    def _stop_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # --- интерфейс для реализации ---
    def _login(self):
        """
        Реализация логина на площадке (если требуется).
        """
        raise NotImplementedError

    def _get_tender_rows(self) -> List:
        """
        Должен вернуть список WebElement-ов (строки таблицы).
        """
        raise NotImplementedError

    def _parse_row(self, row) -> Dict[str, str]:
        """
        Парсинг одной строки — возвращает dict с ключами:
        id, name, description, organizer, url, published, deadline
        """
        raise NotImplementedError

    # --- общая логика ---
    def _match_keywords(self, text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in self.keywords)

    def run(self):
        """
        Запуск парсинга: старт драйвера, логин, сбор строк, фильтрация, пакетная запись в google sheet.
        """
        try:
            self._start_driver()
            self._login()

            rows = self._get_tender_rows()
            print(f"[{self.__class__.__name__}] Найдено строк: {len(rows)}")

            collected_rows = []  # для записи в Google Sheets
            collected_data = []  # для возврата/логирования

            for row in rows:
                try:
                    item = self._parse_row(row)
                except Exception as e:
                    print(f"[{self.__class__.__name__}] Ошибка парсинга строки: {e}")
                    continue

                # проверка по ключевым словам (name + description)
                text_to_check = f"{item.get('name','')} {item.get('description','')}"
                if self.keywords and not self._match_keywords(text_to_check):
                    continue

                # подготавливаем строку для гугл таблицы
                collected_rows.append([
                    item.get('id', ''),
                    item.get('name', ''),
                    item.get('description', ''),
                    item.get('organizer', ''),
                    item.get('url', ''),
                    item.get('published', ''),
                    item.get('deadline', '')
                ])
                collected_data.append(item)

            # запишем пакетно
            self.gs.append_rows(collected_rows)
            print(f"[{self.__class__.__name__}] Собрано и записано тендеров: {len(collected_rows)}")
            return collected_data

        finally:
            self._stop_driver()


# -------------------------------
# B2B implementation
# -------------------------------
class B2BParser(TenderParserBase):
    LOGIN_URL = "https://www.b2b-center.ru/"
    MARKET_URL = "https://www.b2b-center.ru/market/"

    def __init__(self, keywords: List[str], gs_client: GoogleSheetsClient, login: str, password: str,
                 headless: bool = False):
        super().__init__(keywords, gs_client, headless=headless)
        self.login_value = login
        self.password_value = password

    # --- утилиты для безопасного чтения элементов ---
    def _safe_find(self, by, selector, parent=None, timeout=3):
        parent = parent or self.driver
        try:
            return WebDriverWait(parent, timeout).until(EC.presence_of_element_located((by, selector)))
        except Exception:
            return None

    def _safe_text(self, by, selector, parent=None):
        try:
            el = (parent or self.driver).find_element(by, selector)
            return el.text.strip()
        except Exception:
            return ""

    def _safe_attr(self, element, attr):
        try:
            return element.get_attribute(attr)
        except Exception:
            return ""

    # --- реализация интерфейса ---
    def _login(self):
        d = self.driver
        d.get(self.LOGIN_URL)

        # ждем и кликаем кнопку логина
        try:
            login_btn = WebDriverWait(d, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-xid="header-login"]'))
            )
            time.sleep(4)
            login_btn.click()
        except Exception as e:
            print(f"[B2BParser] Не удалось кликнуть кнопку входа: {e}")

        # вводим логин/пароль
        try:
            inp_login = WebDriverWait(d, 20).until(EC.presence_of_element_located((By.ID, "login_control")))
            time.sleep(random.uniform(0.5, 1.5))
            inp_login.send_keys(self.login_value)
        except Exception as e:
            print(f"[B2BParser] Не найдено поле логина: {e}")

        try:
            inp_pass = WebDriverWait(d, 20).until(EC.presence_of_element_located((By.ID, "password_control")))
            time.sleep(random.uniform(0.5, 1.5))
            inp_pass.send_keys(self.password_value)
        except Exception as e:
            print(f"[B2BParser] Не найдено поле пароля: {e}")

        try:
            enter_btn = WebDriverWait(d, 20).until(EC.element_to_be_clickable((By.ID, "enter_button")))
            time.sleep(1)
            enter_btn.click()
        except Exception as e:
            print(f"[B2BParser] Не удалось нажать кнопку отправки: {e}")

        # подождём загрузки и перейдём на страницу рынка
        time.sleep(4)
        d.get(self.MARKET_URL)
        # закрываем возможный модал
        try:
            close_modal = WebDriverWait(d, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.modal-close')))
            time.sleep(4)
            close_modal.click()
        except Exception:
            pass
        # небольшая пауза для загрузки таблицы
        time.sleep(3)

    def _get_tender_rows(self):
        d = self.driver
        WebDriverWait(d, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'table.search-results tbody tr')))
        return d.find_elements(By.CSS_SELECTOR, 'table.search-results tbody tr')

    def _parse_row(self, row) -> Dict[str, str]:
        # пытаемся получить <a> в первом td
        link_el = None
        try:
            link_el = row.find_element(By.CSS_SELECTOR, 'td:first-child a')
        except Exception:
            link_el = None

        # безопасно читаем каждое поле отдельно
        name = ""
        url = ""
        tender_id = ""
        if link_el:
            try:
                name = link_el.text.strip()
            except Exception:
                name = ""
            try:
                url = link_el.get_attribute("href") or ""
            except Exception:
                url = ""
            try:
                tender_id = link_el.get_attribute("data-lot_id") or ""
            except Exception:
                tender_id = ""

        # description
        try:
            description = row.find_element(By.CSS_SELECTOR, 'td:first-child div.search-results-title-desc').text.strip()
        except Exception:
            description = ""

        # organizer
        try:
            organizer_el = row.find_element(By.CSS_SELECTOR, 'td:nth-child(2) a')
            organizer = organizer_el.text.strip()
        except Exception:
            organizer = ""

        # dates
        try:
            published = row.find_element(By.CSS_SELECTOR, 'td:nth-child(3)').text.strip()
        except Exception:
            published = ""
        try:
            deadline = row.find_element(By.CSS_SELECTOR, 'td:nth-child(4)').text.strip()
        except Exception:
            deadline = ""

        return {
            "id": tender_id,
            "name": name,
            "description": description,
            "organizer": organizer,
            "url": url,
            "published": published,
            "deadline": deadline
        }


# -------------------------------
# Пример запуска
# -------------------------------
if __name__ == "__main__":
    # Параметры (подставь свои)
    SERVICE_ACCOUNT_JSON = GOOGLE_CREDS_PATH   # путь к твоему json
    SPREADSHEET_KEY = SPREADSHEET_KEY
    KEYWORDS_FILE = "../keywords.txt"
    LOGIN = B2B_LOGIN
    PASSWORD = B2B_PASSWORD

    # Инициализация
    gs = GoogleSheetsClient(SERVICE_ACCOUNT_JSON, SPREADSHEET_KEY)
    gs.ensure_headers(["ID тендера", "Название", "Описание", "Организатор", "Ссылка", "Дата публикации", "Дата окончания"])
    keywords = KeywordLoader.load(KEYWORDS_FILE)

    parser = B2BParser(keywords=keywords, gs_client=gs, login=LOGIN, password=PASSWORD)
    results = parser.run()

    print(f"Всего найдено/записано: {len(results)}")
