import random
import time
import logging
import re
from typing import List, Set

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import WorksheetNotFound

from settings import *  # GOOGLE_CREDS_PATH, SPREADSHEET_KEY, ZAKUP_KONTUR_LOGIN, ZAKUP_KONTUR_PASS

# -------------------------------
# Логирование
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# -------------------------------
# Google Sheets Helper
# -------------------------------
class GoogleSheetClient:
    HEADERS = ["ID тендера", "Название платформы", "Тип торгов", "Способ отбора",
               "Название", "Описание", "Организатор", "Ссылка", "Дата публикации", "Дата окончания"]

    def __init__(self, creds_path: str, spreadsheet_key: str, worksheet_name: str = "Tenders"):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        self.spreadsheet = client.open_by_key(spreadsheet_key)

        try:
            self.sheet = self.spreadsheet.worksheet(worksheet_name)
            logger.info(f"Используем существующий лист: {worksheet_name}")
        except WorksheetNotFound:
            self.sheet = self.spreadsheet.add_worksheet(title=worksheet_name, rows=2000, cols=10)
            logger.info(f"Создан новый лист: {worksheet_name}")

        if not self.sheet.row_values(1):
            self.sheet.append_row(self.HEADERS)
            logger.info("Добавлены заголовки в Google Sheets")

    def append_row(self, row: List[str]):
        try:
            self.sheet.append_rows([row], value_input_option="RAW")
            logger.info(f"Сохранено в Google Sheets: {row}")
        except Exception as e:
            logger.error(f"Ошибка при добавлении строки в Google Sheets: {e}")


# -------------------------------
# Scraper
# -------------------------------
class KonturScraper:
    PLATFORM_NAME = "Контур"

    def __init__(self, sheet_client: GoogleSheetClient, keywords: List[str]):
        self.sheet = sheet_client
        self.keywords = [kw.lower() for kw in keywords]
        self.seen_links: Set[str] = set()

    def init_driver(self):
        driver = uc.Chrome()
        driver.maximize_window()
        return driver

    def login(self, driver):
        driver.get("https://zakupki.kontur.ru/Login")
        try:
            input_login = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="email"]'))
            )
            time.sleep(random.randint(2, 3))
            input_login.send_keys(ZAKUP_KONTUR_LOGIN)

            input_pass = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="password"]'))
            )
            time.sleep(random.randint(2, 3))
            input_pass.send_keys(ZAKUP_KONTUR_PASS)

            click_log_but = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@data-tid="btn-login"]'))
            )
            time.sleep(2)
            click_log_but.click()
            logger.info("Успешный вход в систему")
            time.sleep(7.5)
        except Exception as e:
            logger.error(f"Ошибка при логине: {e}")

    def set_filters(self, driver):
        checkbox_xpaths = {
            "commis": '//div[@id="Работакомиссии"]//label[@data-tid="Checkbox__root"]',
            "ends": '//div[@id="Завершены"]//label[@data-tid="Checkbox__root"]',
            "plans": '//div[@id="Планируются"]//label[@data-tid="Checkbox__root"]',
            "passed": '//div[@id="Отменены"]//label[@data-tid="Checkbox__root"]'
        }

        for name, xpath in checkbox_xpaths.items():
            try:
                el = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                time.sleep(1)
                el.click()
                logger.info(f"Выбран фильтр: {name}")
            except Exception as e:
                logger.warning(f"Не удалось выбрать фильтр {name}: {e}")

        # Нажимаем поиск
        try:
            click_find = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//span[@data-tid="find_button"]'))
            )
            time.sleep(1)
            click_find.click()
            logger.info("Поиск запущен")
            time.sleep(4)
        except Exception as e:
            logger.error(f"Ошибка при клике поиска: {e}")

    def collect_links(self, driver) -> List[str]:
        all_links = []
        page = 0

        while True:
            page += 1
            logger.info(f"Сбор ссылок, страница {page}")
            time.sleep(4)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            try:
                cards = soup.find_all("div", class_="purchase-card")
                for card in cards:
                    try:
                        link_tag = card.select_one("a.purchase-card__order-name")
                        if not link_tag or not link_tag.get("href"):
                            continue
                        card_text = card.get_text(" ", strip=True).lower()
                        if any(kw in card_text for kw in self.keywords):
                            href = link_tag["href"]
                            if href not in self.seen_links:
                                all_links.append(href)
                                self.seen_links.add(href)
                    except Exception as inner_e:
                        logger.warning(f"Ошибка обработки карточки: {inner_e}")
            except Exception as e:
                logger.error(f"Ошибка при сборе ссылок: {e}")

            # Переход на следующую страницу
            try:
                next_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//a[@class="paging-link custom-paging__next"]'))
                )
                logger.info("Переходим на следующую страницу")
                next_btn.click()
            except Exception:
                break

        logger.info(f"Всего ссылок собрано: {len(all_links)}")
        return all_links

    def parse_and_save(self, driver, links: List[str]):
        for link in links:
            try:
                driver.get(link)
                time.sleep(2)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                data = {}

                data["platform_id"] = link.rstrip("/").split("/")[-1]
                data["link"] = link
                data["name"] = (soup.select_one("h1.tender-block__title").get_text(strip=True)
                                if soup.select_one("h1.tender-block__title") else "--")
                data["selection_method"] = (soup.select_one("div.purchase-type__title").get_text(strip=True)
                                            if soup.select_one("div.purchase-type__title") else "--")
                data["type"] = (soup.select_one(".purchase-page__block.tender-block.purchase-placement .tender-named-values_value")
                                .get_text(" ", strip=True) if soup.select_one(
                                    ".purchase-page__block.tender-block.purchase-placement .tender-named-values_value") else "--")
                data["description"] = (soup.select_one("div.purchase-description__publication-info").get_text(" ", strip=True)
                                       if soup.select_one("div.purchase-description__publication-info") else "--")
                data["organizer"] = (soup.select_one("div.lot-customer__info").get_text(" ", strip=True)
                                     if soup.select_one("div.lot-customer__info") else "--")
                # Дата публикации
                pub_tag = soup.select_one("div.purchase-description__publication-info")
                if pub_tag:
                    match = re.search(r"опубликован\s+([\d\.]+\s[\d:]+)", pub_tag.get_text(" ", strip=True))
                    data["publish_date"] = match.group(1) if match else "--"
                else:
                    data["publish_date"] = "--"
                # Дата окончания
                date_tag = soup.select_one("span[data-tid='p-date__date']")
                data["deadline"] = date_tag.get_text(strip=True) if date_tag else "--"

                row = [
                    data["platform_id"],
                    self.PLATFORM_NAME,
                    data.get("type", "--"),
                    data.get("selection_method", "--"),
                    data["name"],
                    data["description"],
                    data["organizer"],
                    data["link"],
                    data["publish_date"],
                    data["deadline"],
                ]

                self.sheet.append_row(row)
            except Exception as e:
                logger.error(f"Ошибка при обработке ссылки {link}: {e}")

    def run(self):
        driver = self.init_driver()
        try:
            self.login(driver)
            self.set_filters(driver)
            links = self.collect_links(driver)
            self.parse_and_save(driver, links)
        finally:
            try:
                driver.quit()
            except Exception:
                pass


# -------------------------------
# Загрузка ключевых слов
# -------------------------------
def load_keywords(path: str = "../keywords.txt") -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Не удалось загрузить keywords: {e}")
        return []


# -------------------------------
# Запуск
# -------------------------------
if __name__ == "__main__":
    keywords = load_keywords("../keywords.txt")
    sheet_client = GoogleSheetClient(GOOGLE_CREDS_PATH, SPREADSHEET_KEY)
    scraper = KonturScraper(sheet_client, keywords)
    scraper.run()
