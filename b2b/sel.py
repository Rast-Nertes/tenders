import random
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -------------------------------
# Google Sheets
# -------------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("../tenders-471321-0956d325050a.json", scope)
client = gspread.authorize(creds)

sheet_title = "Tenders"  # используем существующую таблицу
spreadsheet = client.open_by_key("1smGDKdadXigDZ79QvChQH9LIY85BtsjvTBiCOLgLIS0")
sheet = spreadsheet.sheet1

# -------------------------------
# Загружаем ключевые слова
# -------------------------------
with open("../keywords.txt", "r", encoding="utf-8") as f:
    keywords = [line.strip().lower() for line in f if line.strip()]


# Добавляем заголовки (один раз)
try:
    if not sheet.row_values(1):
        headers = ["ID тендера", "Название", "Описание", "Организатор", "Ссылка", "Дата публикации", "Дата окончания"]
        sheet.append_row(headers)
except Exception as e:
    print(f"Ошибка при добавлении заголовков: {e}")

# -------------------------------
# Selenium
# -------------------------------


def init_driver():
    driver = uc.Chrome(version_main=139)
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
        input_login.send_keys("technologystudiorv@gmail.com")

        input_pass = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="password_control"]'))
        )
        time.sleep(random.randint(1, 2))
        input_pass.send_keys("ywK-S89-bP5-zYA")

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
        close_modal.click()
    except:
        pass

    # Получаем тендеры
    tenders_data = []
    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'table.search-results tbody tr'))
        )
        tenders = driver.find_elements(By.CSS_SELECTOR, 'table.search-results tbody tr')

        for row in tenders:
            link_element = row.find_element(By.CSS_SELECTOR, 'td:first-child a')
            try:
                tender_name = link_element.text.strip()
            except: tender_name = "--"

            try:
                tender_url = link_element.get_attribute('href')
            except: tender_url = "--"

            try:
                description = row.find_element(By.CSS_SELECTOR,
                                           'td:first-child div.search-results-title-desc').text.strip()
            except: description = "--"

            try:
                organizer = row.find_element(By.CSS_SELECTOR, 'td:nth-child(2) a').text.strip()
            except: organizer = "--"

            try:
                published = row.find_element(By.CSS_SELECTOR, 'td:nth-child(3)').text.strip()
            except: published = "--"

            try:
                deadline = row.find_element(By.CSS_SELECTOR, 'td:nth-child(4)').text.strip()
            except: deadline = "--"

            try:
                tender_id = link_element.get_attribute('data-lot_id')
            except: tender_id = "--"

            # -------------------------------
            # Фильтрация по ключевым словам
            # -------------------------------
            text_to_check = f"{tender_name} {description}".lower()
            if not any(keyword in text_to_check for keyword in keywords):
                continue  # ключевых слов нет, пропускаем

            # -------------------------------
            # Записываем сразу в Google Sheets
            # -------------------------------
            sheet.append_row([
                tender_id, tender_name, description,
                organizer, tender_url, published, deadline
            ])

            tenders_data.append({
                'id': tender_id,
                'name': tender_name,
                'description': description,
                'organizer': organizer,
                'url': tender_url,
                'published': published,
                'deadline': deadline
            })

    except Exception as e:
        print(f"ERROR GET TENDERS {e}")

    print(f"Собрано {len(tenders_data)} тендеров")
    driver.quit()


if __name__ == "__main__":
    init_driver()
