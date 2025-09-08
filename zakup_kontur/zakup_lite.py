import random
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from settings import *
from oauth2client.service_account import ServiceAccountCredentials
import gspread.exceptions

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "../tenders-471321-0956d325050a.json", scope
)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key("1smGDKdadXigDZ79QvChQH9LIY85BtsjvTBiCOLgLIS0")
sheet_main = spreadsheet.sheet1   # "Tenders"

try:
    sheet_kontur = spreadsheet.worksheet("Kontur")
except gspread.exceptions.WorksheetNotFound:
    sheet_kontur = spreadsheet.add_worksheet(title="Kontur", rows=2000, cols=10)

if not sheet_kontur.row_values(1):
    headers = ["ID тендера", "Название", "Описание", "Организатор", "Ссылка", "Дата публикации", "Дата окончания"]
    sheet_kontur.append_row(headers)


with open("../keywords.txt", "r", encoding="utf-8") as f:
    keywords = [line.strip().lower() for line in f if line.strip()]


def init_driver():
    driver = uc.Chrome(version_main=139)
    driver.maximize_window()
    driver.get("https://zakupki.kontur.ru/Login")

    # Логин

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

        time.sleep(7.5)
    except Exception as e:
        print(f"ERROR LOGIN {e}")

    # Checkboxes
    try:
        click_checkbox_commis = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@id="Работакомиссии"]//label[@data-tid="Checkbox__root"]'))
        )
        time.sleep(1)
        click_checkbox_commis.click()
    except Exception as e:
        print(f"ERROR COMISSION CHECKBOX {e}")

    try:
        click_checkbox_ends = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@id="Завершены"]//label[@data-tid="Checkbox__root"]'))
        )
        time.sleep(1)
        click_checkbox_ends.click()
    except Exception as e:
        print(f"ERROR ENDS CHECKBOX {e}")

    try:
        click_checkbox_plans = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@id="Планируются"]//label[@data-tid="Checkbox__root"]'))
        )
        time.sleep(1)
        click_checkbox_plans.click()
    except Exception as e:
        print(f"ERROR PLANS CHECKBOX {e}")

    try:
        click_checkbox_passed = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@id="Отменены"]//label[@data-tid="Checkbox__root"]'))
        )
        time.sleep(1)
        click_checkbox_passed.click()
    except Exception as e:
        print(f"ERROR PASSED CHECKBOX {e}")

    # End Checkboxes

    try:
        click_find = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//span[@data-tid="find_button"]'))
        )
        time.sleep(1)
        click_find.click()
    except Exception as e:
        print(f'ERROR FIND BUTT {e}')

    time.sleep(4)

    try:
        page = 0
        while True:
            try:
                find_next_page = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//a[@class="paging-link custom-paging__next"]'))
                )
                print(f"NEXT BUT FIND!")
            except:
                break

            page += 1
            print(f"PAGE NUM {page} \n")
            time.sleep(4)
            page_src = driver.page_source
            soup = BeautifulSoup(page_src)

            results = []
            rows_to_write = []
            try:
                cards = soup.find_all("div", class_="purchase-card")
                for card in cards:
                    data = {}

                    # 1. идентификатор тендера на площадке-источнике
                    data["platform_id"] = card.get("data-card")

                    # 2. Регистрационный номер (внутри блока notification-info)
                    notif = card.find("div", class_="purchase-card__notification-info")
                    reg_number = None

                    if notif:
                        spans = notif.find_all("span")
                        publish_date_tag = notif.find("span", class_="purchase-card__publish-date")

                        for sp in spans:
                            # пропускаем "Казахстан" и дату
                            if "sng-label" in sp.get("class", []):
                                continue
                            if sp == publish_date_tag:
                                continue
                            reg_number = sp.get_text(strip=True)

                    data["reg_number"] = reg_number

                    # 3. Наименование тендера
                    name_tag = card.select_one("a.purchase-card__order-name span")
                    data["name"] = name_tag.get_text(strip=True) if name_tag else None

                    # 4. Ссылка на тендер (основная)
                    link_tag = card.select_one("a.purchase-card__order-name")
                    data["link"] = link_tag["href"] if link_tag else None

                    # 5. Статус тендера
                    status_tag = card.select_one(".purchase-card__status-col span")
                    data["status"] = status_tag.get_text(" ", strip=True) if status_tag else None

                    # 6. Дата публикации
                    pub_tag = card.select_one("span.purchase-card__publish-date")
                    data["publish_date"] = (
                        pub_tag.get_text(strip=True).replace("от ", "") if pub_tag else None
                    )

                    # 7. Дата окончания подачи заявок
                    deadline_tag = card.select_one(".purchase-card__status-col span")
                    deadline = None
                    if deadline_tag and "до" in deadline_tag.text:
                        # пример: "Подача заявок до 09.09.2025 11:00 МСК"
                        txt = deadline_tag.get_text(" ", strip=True)
                        parts = txt.split("до")
                        if len(parts) > 1:
                            deadline = parts[1].strip()
                    data["deadline"] = deadline

                    # 8. Организатор — сначала p.purchase-card__customer, иначе span.purchase-card__ep a
                    org = None
                    org_tag = card.find("p", class_="purchase-card__customer")
                    if org_tag:
                        org = org_tag.get_text(strip=True)
                    else:
                        ep_link = card.select_one("span.purchase-card__ep a")
                        if ep_link:
                            org = ep_link.get_text(" ", strip=True)
                    data["organizer"] = org

                    # ---- фильтрация ----

                    text_to_check = " ".join([
                        data.get("name") or "",
                        data.get("status") or "",
                        data.get("organizer") or "",
                    ]).lower()

                    if any(kw in text_to_check for kw in keywords):
                        row = [
                            data.get("platform_id", ""),
                            data.get("name", ""),
                            data.get("status", ""),
                            data.get("organizer", ""),
                            data.get("link", ""),
                            data.get("publish_date", ""),
                            data.get("deadline", ""),
                        ]
                        rows_to_write.append(row)
                        results.append(data)

                if rows_to_write:
                    sheet_kontur.append_rows(rows_to_write, value_input_option="RAW")

                for r in rows_to_write:
                    print("Сохранено:", r)

            except Exception as e:
                print(f"ERROR GET CARDS {e}")

            try:
                find_next_page.click()
            except:
                ...

    finally:
        # обязательно закрываем браузер
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    init_driver()
