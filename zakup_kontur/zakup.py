import random
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import gspread.exceptions
from settings import *


# ---- Класс для работы с Google Sheets ----
class GoogleSheet:
    def __init__(self, json_file, spreadsheet_key, sheet_name="Kontur"):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_file, scope)
        client = gspread.authorize(creds)
        self.sheet = self._get_sheet(client, spreadsheet_key, sheet_name)
        self.existing_ids = set(self.sheet.col_values(1))  # для проверки дубликатов

    def _get_sheet(self, client, key, sheet_name):
        spreadsheet = client.open_by_key(key)
        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(title=sheet_name, rows=2000, cols=10)
        if not sheet.row_values(1):
            headers = ["ID тендера", "Название", "Описание", "Организатор", "Ссылка", "Дата публикации", "Дата окончания"]
            sheet.append_row(headers)
        return sheet

    def append_rows(self, rows):
        rows_to_add = []
        for row in rows:
            if row[0] not in self.existing_ids:
                rows_to_add.append(row)
                self.existing_ids.add(row[0])
        if rows_to_add:
            self.sheet.append_rows(rows_to_add, value_input_option="RAW")
            for r in rows_to_add:
                print("Сохранено:", r)


# ---- Класс для хранения данных о тендере ----
class Tender:
    def __init__(self, platform_id, name, status, organizer, link, publish_date, deadline):
        self.platform_id = platform_id
        self.name = name
        self.status = status
        self.organizer = organizer
        self.link = link
        self.publish_date = publish_date
        self.deadline = deadline

    def to_row(self):
        return [
            self.platform_id,
            self.name,
            self.status,
            self.organizer,
            self.link,
            self.publish_date,
            self.deadline
        ]


# ---- Класс для скрапинга контента с Kontur ----
class KonturScraper:
    def __init__(self, email, password, keywords, sheet: GoogleSheet):
        self.email = email
        self.password = password
        self.keywords = [kw.lower() for kw in keywords]
        self.sheet = sheet
        self.driver = None

    def start(self):
        self.driver = uc.Chrome(version_main=139)
        self.driver.maximize_window()
        self.driver.get("https://zakupki.kontur.ru/Login")
        self.login()
        self.set_checkboxes()
        self.find_tenders()
        self.driver.quit()

    def login(self):
        try:
            input_login = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="email"]'))
            )
            time.sleep(random.randint(2, 3))
            input_login.send_keys(self.email)

            input_pass = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="password"]'))
            )
            time.sleep(random.randint(2, 3))
            input_pass.send_keys(self.password)

            click_log_but = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@data-tid="btn-login"]'))
            )
            time.sleep(2)
            click_log_but.click()
            time.sleep(7.5)
        except Exception as e:
            print(f"ERROR LOGIN {e}")

    def set_checkboxes(self):
        checkbox_ids = ["Работакомиссии", "Завершены", "Планируются", "Отменены"]
        for cid in checkbox_ids:
            try:
                click_checkbox = WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, f'//div[@id="{cid}"]//label[@data-tid="Checkbox__root"]'))
                )
                time.sleep(1)
                click_checkbox.click()
            except Exception as e:
                print(f"ERROR {cid} CHECKBOX {e}")

        try:
            click_find = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//span[@data-tid="find_button"]'))
            )
            time.sleep(1)
            click_find.click()
        except Exception as e:
            print(f'ERROR FIND BUTTON {e}')

        time.sleep(4)

    def find_tenders(self):
        page = 0
        while True:
            page += 1
            print(f"PAGE NUM {page}")
            time.sleep(4)
            page_src = self.driver.page_source
            soup = BeautifulSoup(page_src, "html.parser")
            rows_to_write = []

            try:
                cards = soup.find_all("div", class_="purchase-card")
                for card in cards:
                    tender = self.parse_card(card)
                    text_to_check = " ".join([tender.name or "", tender.status or "", tender.organizer or ""]).lower()
                    if any(kw in text_to_check for kw in self.keywords):
                        rows_to_write.append(tender.to_row())
            except Exception as e:
                print(f"ERROR GET CARDS {e}")

            self.sheet.append_rows(rows_to_write)

            # Переход на следующую страницу
            try:
                find_next_page = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//a[@class="paging-link custom-paging__next"]'))
                )
                find_next_page.click()
            except:
                break

    @staticmethod
    def parse_card(card):
        platform_id = card.get("data-card")
        notif = card.find("div", class_="purchase-card__notification-info")
        reg_number = None
        if notif:
            spans = notif.find_all("span")
            publish_date_tag = notif.find("span", class_="purchase-card__publish-date")
            for sp in spans:
                if "sng-label" in sp.get("class", []):
                    continue
                if sp == publish_date_tag:
                    continue
                reg_number = sp.get_text(strip=True)

        name_tag = card.select_one("a.purchase-card__order-name span")
        name = name_tag.get_text(strip=True) if name_tag else None

        link_tag = card.select_one("a.purchase-card__order-name")
        link = link_tag["href"] if link_tag else None

        status_tag = card.select_one(".purchase-card__status-col span")
        status = status_tag.get_text(" ", strip=True) if status_tag else None

        pub_tag = card.select_one("span.purchase-card__publish-date")
        publish_date = pub_tag.get_text(strip=True).replace("от ", "") if pub_tag else None

        deadline_tag = card.select_one(".purchase-card__status-col span")
        deadline = None
        if deadline_tag and "до" in deadline_tag.text:
            txt = deadline_tag.get_text(" ", strip=True)
            parts = txt.split("до")
            if len(parts) > 1:
                deadline = parts[1].strip()

        org_tag = card.find("p", class_="purchase-card__customer")
        if org_tag:
            organizer = org_tag.get_text(strip=True)
        else:
            ep_link = card.select_one("span.purchase-card__ep a")
            organizer = ep_link.get_text(" ", strip=True) if ep_link else None

        return Tender(platform_id, name, status, organizer, link, publish_date, deadline)


# ---- MAIN ----
if __name__ == "__main__":
    with open("../keywords.txt", "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

    sheet = GoogleSheet(GOOGLE_CREDS_PATH, SPREADSHEET_KEY)
    scraper = KonturScraper(ZAKUP_KONTUR_LOGIN, ZAKUP_KONTUR_PASS, keywords, sheet)
    scraper.start()
