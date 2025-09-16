import random
import time
from urllib.parse import urljoin

from settings import *
import gspread
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -------------------------------
# Google Sheets
# -------------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_PATH, scope)
client = gspread.authorize(creds)

sheet_title = "Tenders"  # используем существующую таблицу
spreadsheet = client.open_by_key(SPREADSHEET_KEY)
sheet = spreadsheet.sheet1

# -------------------------------
# Загружаем ключевые слова
# -------------------------------
with open("../keywords.txt", "r", encoding="utf-8") as f:
    keywords = [line.strip().lower() for line in f if line.strip()]

BASE = "https://www.b2b-center.ru"
PLATFORM_NAME = "B2B"

# Добавляем заголовки (один раз)
try:
    if not sheet.row_values(1):
        headers = ["ID тендера", "Название платформы", "Тип торгов", "Способ отбора", "Название", "Описание",
                   "Организатор", "Ссылка", "Дата публикации", "Дата окончания"]
        sheet.append_row(headers)
except Exception as e:
    print(f"Ошибка при добавлении заголовков: {e}")

# -------------------------------
# Selenium
# -------------------------------


def init_driver():
    driver = uc.Chrome()
    driver.maximize_window()
    driver.get("https://www.b2b-center.ru/")

    # Логин
    try:
        login_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-xid="header-login"]'))
        )
        time.sleep(5)
        login_btn.click()
    except Exception as e:
        print(f"ERROR CLICL LOG BUTT {e}")

    try:
        input_login = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="login_control"]'))
        )
        time.sleep(random.randint(1, 2))
        input_login.send_keys(B2B_LOGIN)

        input_pass = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="password_control"]'))
        )
        time.sleep(random.randint(1, 2))
        input_pass.send_keys(B2B_PASSWORD)

        click_log_but = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="enter_button"]'))
        )
        time.sleep(2)
        click_log_but.click()

        time.sleep(7.5)
        driver.get("https://www.b2b-center.ru/market/")

    except Exception as e:
        print(f"ERROR LOGIN {e}")

    # Закрываем модальное окно
    try:
        close_modal = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'span.modal-close'))
        )
        time.sleep(5)
        close_modal.click()
    except:
        pass

    from_ = 0
    driver.get(
        f"{BASE}/market/?searching=1&company_type=2&price_currency=0&date=1&trade=all&purchase_223fz=1&from={from_}#search-result")
    time.sleep(3)

    all_links = []
    seen = set()
    page = 0

    while True:
        page += 1
        print(f"[PAGE {page}] loading from={from_}")
        try:
            # ждем, пока появится таблица
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.search-results tbody tr"))
            )
        except Exception as e:
            print(f"[PAGE {page}] Таблица не загрузилась: {e}")
            break

        # получаем строки
        rows = driver.find_elements(By.CSS_SELECTOR, "table.search-results tbody tr")
        if not rows:
            print(f"[PAGE {page}] Нет строк — выходим")
            break

        added_this_page = 0
        for r in rows:
            try:
                # основной линк / название
                link_el = r.find_element(By.CSS_SELECTOR, "a.search-results-title")
                href = link_el.get_attribute("href") or ""
                # описание внутри карточки (если есть)
                try:
                    desc_el = r.find_element(By.CSS_SELECTOR, "div.search-results-title-desc")
                    desc = desc_el.text.strip()
                except:
                    desc = ""
                # организатор
                try:
                    organizer = r.find_element(By.CSS_SELECTOR, "td:nth-child(2) a").text.strip()
                except:
                    organizer = ""
                # название (в тексте ссылки может быть и номер тендера + название)
                try:
                    name = link_el.text.strip()
                except:
                    name = ""

                text_to_check = " ".join([name, desc, organizer]).lower()

                # фильтрация по ключевым словам
                if any(kw in text_to_check for kw in keywords):
                    full_url = urljoin(BASE, href)
                    if full_url not in seen:
                        seen.add(full_url)
                        all_links.append(full_url)
                        added_this_page += 1
            except Exception as e: continue

        print(
            f"[PAGE {page}] найдено подходящих ссылок на странице: {added_this_page} (всего собрано: {len(all_links)})")

        time.sleep(2)
        try:
            # ищем элементы пагинации
            controls = driver.find_elements(By.CSS_SELECTOR, "div.pagi-ctrl")
            if not controls:
                print("Пагинация: контролы не найдены — считаем последнюю страницу.")
                break

            # проверяем наличие текста "Alt" в любом из контролов
            has_alt = any(("Alt" in (c.text or "")) for c in controls)
            if not has_alt:
                print("Пагинация: 'Alt' не найден в контролах — выходим.")
                break

            # если "Alt" есть — просто формируем следующий URL и переходим
            from_ += 20
            next_url = f"https://www.b2b-center.ru/market/?searching=1&company_type=2&price_currency=0&date=1&trade=all&purchase_223fz=1&from={from_}#search-result"
            print("Переходим на следующую страницу:", next_url)
            driver.get(next_url)
            time.sleep(4)

        except Exception as e:
            print(f"Ошибка при проверке/переходе по пагинации: {e}")
            break

        from_ += 20
        next_url = f"{BASE}/market/?searching=1&company_type=2&price_currency=0&date=1&trade=all&purchase_223fz=1&from={from_}#search-result"
        driver.get(next_url)
        time.sleep(2)

    print("\nСбор ссылок завершён. Всего ссылок:", len(all_links))
    for u in all_links:
        print(u)

    time.sleep(3)
    for link in all_links:
        driver.get(link)
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        try:
            fav_span = soup.select_one("span.favorite-container")
            tender_id = fav_span["data-id"] if fav_span else "--"
        except:
            tender_id = "--"

        # Тип торгов
        try:
            time.sleep(1)
            trade_type_el = driver.find_element(By.XPATH, '//tr[@class="c2"]//td//strong')
            trade_type = trade_type_el.text.strip()
        except Exception as e:
            print(f"ERROR TYPE OF TRADE {e}")
            trade_type = "--"

        # Ссылка
        try:
            link_tender = link
        except:
            link_tender = '--'

        # Название
        try:
            title = soup.find("div", class_="s2").get_text(strip=True)
        except:
            title = '--'

        try:
            desc = "--"
        except:
            desc = "--"

        try:
            organizer_name = organizer_row = soup.find("tr", id="trade-info-organizer-name")
            organizer = organizer_row.find("td").find_next("td").get_text(strip=True)
        except Exception:
            organizer = '--'

        # Дата публикации
        try:
            date_pub_tag = soup.find("tr", id="trade_info_date_begin")
            date_pub = date_pub_tag.find_all("td")[1].get_text(strip=True)
        except: date_pub = '--'

        # Дата окончания
        try:
            date_end_tag = soup.find("tr", id="trade_info_date_end")
            date_end = date_end_tag.find_all("td")[1].get_text(strip=True)
        except: date_end = '--'

        row = [
            tender_id,
            PLATFORM_NAME,
            trade_type,  # Тип торгов
            "--",  # Способ отбора (можно тоже type_of_trade или другое поле)
            title,
            "--",
            organizer,
            link,
            date_pub,
            date_end,
        ]

        # Сохраняем в таблицу
        try:
            sheet.append_row(row, value_input_option="RAW")
            print("Сохранено:", row)
        except Exception as e:
            print("ERROR APPENDING ROW:", e)

    driver.quit()


if __name__ == "__main__":
    init_driver()
