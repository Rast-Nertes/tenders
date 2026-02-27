import random
import time
from urllib.parse import urljoin
from typing import List, Set

from settings import *  # GOOGLE_CREDS_PATH, SPREADSHEET_KEY, B2B_LOGIN, B2B_PASSWORD
import gspread
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# -------------------------------
# Google Sheets helper 
# -------------------------------
class GoogleSheetClient:
    HEADERS = ["ID тендера", "Название платформы", "Тип торгов", "Способ отбора", "Название", "Описание",
               "Организатор", "Ссылка", "Дата публикации", "Дата окончания"]

    def __init__(self, creds_path: str, spreadsheet_key: str):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        self.spreadsheet = client.open_by_key(spreadsheet_key)
        self.sheet = self.spreadsheet.sheet1
        self._ensure_headers()

    def _ensure_headers(self):
        try:
            first_row = self.sheet.row_values(1)
            if not first_row:
                self.sheet.append_row(self.HEADERS)
                print("Добавлены заголовки в таблицу.")
        except Exception as e:
            print("Ошибка при добавлении заголовков:", e)

    def append_row(self, row: List[str]):
        try:
            self.sheet.append_row(row, value_input_option="RAW")
            print("Сохранено в Google Sheets:", row)
        except Exception as e:
            print("ERROR APPENDING ROW:", e)


# -------------------------------
# Scraper (Selenium + BS4)
# -------------------------------
class B2BScraper:
    BASE = "https://www.b2b-center.ru"
    PLATFORM_NAME = "B2B"
    SEARCH_URL_TEMPLATE = (BASE + "/market/?searching=1&company_type=2&price_currency=0&date=1"
                           "&trade=all&purchase_223fz=1&from={from_}#search-result")

    def __init__(self, sheet_client: GoogleSheetClient, keywords: List[str]):
        self.sheet = sheet_client
        self.keywords = [k.lower() for k in keywords]
        self.seen: Set[str] = set()

    def init_driver(self):
        driver = uc.Chrome()
        driver.maximize_window()
        return driver

    def login_and_navigate(self, driver):
        driver.get(self.BASE)
        try:
            login_btn = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-xid="header-login"]'))
            )
            time.sleep(1)
            login_btn.click()
        except Exception as e:
            print("ERROR CLICK LOGIN BUTTON:", e)

        try:
            input_login = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="login_control"]'))
            )
            time.sleep(random.uniform(0.5, 1.5))
            input_login.send_keys(B2B_LOGIN)

            input_pass = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="password_control"]'))
            )
            time.sleep(random.uniform(0.5, 1.5))
            input_pass.send_keys(B2B_PASSWORD)

            click_log_but = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="enter_button"]'))
            )
            time.sleep(1)
            click_log_but.click()

            # даём время на логин
            time.sleep(6)
            driver.get(self.SEARCH_URL_TEMPLATE.format(from_=0))
            time.sleep(2)
        except Exception as e:
            print("ERROR DURING LOGIN:", e)

        # закрываем модалки, если есть
        try:
            close_modal = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.modal-close'))
            )
            time.sleep(1)
            close_modal.click()
        except Exception:
            pass

    def collect_links(self, driver) -> List[str]:
        all_links: List[str] = []
        from_ = 0
        page = 0

        while True:
            page += 1
            url = self.SEARCH_URL_TEMPLATE.format(from_=from_)
            print(f"[PAGE {page}] Получаем: {url}")
            driver.get(url)
            time.sleep(2)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.search-results tbody tr"))
                )
            except Exception as e:
                print(f"[PAGE {page}] Таблица не загрузилась: {e}")
                break

            rows = driver.find_elements(By.CSS_SELECTOR, "table.search-results tbody tr")
            if not rows:
                print(f"[PAGE {page}] Нет строк — выходим")
                break

            added_this_page = 0
            for r in rows:
                try:
                    link_el = r.find_element(By.CSS_SELECTOR, "a.search-results-title")
                    href = link_el.get_attribute("href") or ""
                    try:
                        desc_el = r.find_element(By.CSS_SELECTOR, "div.search-results-title-desc")
                        desc = desc_el.text.strip()
                    except:
                        desc = ""
                    try:
                        organizer = r.find_element(By.CSS_SELECTOR, "td:nth-child(2) a").text.strip()
                    except:
                        organizer = ""
                    try:
                        name = link_el.text.strip()
                    except:
                        name = ""

                    text_to_check = " ".join([name, desc, organizer]).lower()
                    if any(kw in text_to_check for kw in self.keywords):
                        full_url = urljoin(self.BASE, href)
                        if full_url not in self.seen:
                            self.seen.add(full_url)
                            all_links.append(full_url)
                            added_this_page += 1
                except Exception:
                    continue

            print(f"[PAGE {page}] найдено на странице: {added_this_page}, всего собрано: {len(all_links)}")

            # простая логика пагинации: если на странице есть контролы 'pagi-ctrl' и текст 'Alt' — идём дальше
            try:
                controls = driver.find_elements(By.CSS_SELECTOR, "div.pagi-ctrl")
                if not controls:
                    print("Пагинация: контролы не найдены — останавливаемся.")
                    break
                has_alt = any(("Alt" in (c.text or "")) for c in controls)
                if not has_alt:
                    print("Пагинация: 'Alt' не найден — считаем последняя страница.")
                    break
            except Exception as e:
                print("Ошибка при проверке пагинации:", e)
                break

            from_ += 20
            # безопасный предел, чтобы не зациклиться бесконечно (можно убрать/увеличить)
            if from_ > 1000:
                print("Достигнут лимит страниц, останавливаемся.")
                break

            time.sleep(1)

        print("Сбор ссылок завершён. Всего:", len(all_links))
        return all_links

    def parse_and_save(self, driver, links: List[str]):
        for link in links:
            try:
                driver.get(link)
                time.sleep(2)
                soup = BeautifulSoup(driver.page_source, "html.parser")

                # tender_id
                try:
                    fav_span = soup.select_one("span.favorite-container")
                    tender_id = fav_span["data-id"] if fav_span else "--"
                except:
                    tender_id = "--"

                # Тип торгов (попытка через Selenium, fallback через soup)
                try:
                    trade_type_el = driver.find_element(By.XPATH, '//tr[@class="c2"]//td//strong')
                    trade_type = trade_type_el.text.strip()
                except Exception:
                    try:
                        trade_type = soup.select_one('tr.c2 td strong').get_text(strip=True)
                    except:
                        trade_type = "--"

                # Название
                try:
                    title = soup.find("div", class_="s2").get_text(strip=True)
                except:
                    title = '--'

                # Организатор
                try:
                    organizer_row = soup.find("tr", id="trade-info-organizer-name")
                    organizer = organizer_row.find_all("td")[1].get_text(strip=True)
                except Exception:
                    organizer = '--'

                # Дата публикации / окончания
                try:
                    date_pub_tag = soup.find("tr", id="trade_info_date_begin")
                    date_pub = date_pub_tag.find_all("td")[1].get_text(strip=True)
                except:
                    date_pub = '--'

                try:
                    date_end_tag = soup.find("tr", id="trade_info_date_end")
                    date_end = date_end_tag.find_all("td")[1].get_text(strip=True)
                except:
                    date_end = '--'

                row = [
                    tender_id,
                    self.PLATFORM_NAME,
                    trade_type,
                    "--",  # Способ отбора
                    title,
                    "--",  # Описание (можно вытянуть при необходимости)
                    organizer,
                    link,
                    date_pub,
                    date_end,
                ]

                self.sheet.append_row(row)

            except Exception as e:
                print(f"Ошибка при парсинге {link}: {e}")
                continue

    def run(self):
        driver = self.init_driver()
        try:
            self.login_and_navigate(driver)
            links = self.collect_links(driver)
            self.parse_and_save(driver, links)
        finally:
            try:
                driver.quit()
            except Exception:
                pass


# -------------------------------
# Утилита: загрузка ключевых слов 
# -------------------------------
def load_keywords(path: str = "../keywords.txt") -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    except Exception as e:
        print("Не удалось загрузить keywords:", e)
        return []


# -------------------------------
# Запуск
# -------------------------------
if __name__ == "__main__":
    keywords = load_keywords("../keywords.txt")
    sheet_client = GoogleSheetClient(GOOGLE_CREDS_PATH, SPREADSHEET_KEY)
    scraper = B2BScraper(sheet_client, keywords)
    scraper.run()
