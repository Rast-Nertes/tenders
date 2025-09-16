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

platform_z = "Контур"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    GOOGLE_CREDS_PATH, scope
)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_KEY)
sheet_main = spreadsheet.sheet1   # "Tenders"

try:
    sheet_kontur = spreadsheet.worksheet("Tenders")
except gspread.exceptions.WorksheetNotFound:
    sheet_kontur = spreadsheet.add_worksheet(title="Kontur", rows=2000, cols=10)

if not sheet_kontur.row_values(1):
    headers = ["ID тендера", "Название платформы", "Тип торгов", "Способ отбора", "Название", "Описание", "Организатор", "Ссылка", "Дата публикации", "Дата окончания"]
    sheet_kontur.append_row(headers)


with open("../keywords.txt", "r", encoding="utf-8") as f:
    keywords = [line.strip().lower() for line in f if line.strip()]


def init_driver():
    driver = uc.Chrome()
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

    all_links = []
    seen_links = set()

    try:
        page = 0
        while True:
            page += 1
            print(f"PAGE NUM {page} \n")
            time.sleep(4)
            page_src = driver.page_source
            soup = BeautifulSoup(page_src, "html.parser")  # явный парсер

            try:
                # Сбор всех ссылок на тендеры — теперь с фильтрацией по ключевым словам (по всему тексту карточки)
                cards = soup.find_all("div", class_="purchase-card")
                for card in cards:
                    try:
                        link_tag = card.select_one("a.purchase-card__order-name")
                        if not link_tag or not link_tag.get("href"):
                            continue

                        # Берём весь текст карточки и приводим к lower для сравнения с keywords
                        card_text = card.get_text(" ", strip=True).lower()

                        # если хоть одно ключевое слово совпало — добавляем ссылку
                        if any(kw in card_text for kw in keywords):
                            href = link_tag["href"]
                            if href not in seen_links:
                                all_links.append(href)
                                seen_links.add(href)
                    except Exception as inner_e:
                        # локально логируем проблему с отдельной карточкой и продолжаем
                        print(f"ERROR PROCESS CARD: {inner_e}")
                        continue
            except Exception as e:
                print(f'ERROR GET LINKS {e}')

            try:
                find_next_page = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//a[@class="paging-link custom-paging__next"]'))
                )
                print(f"NEXT BUT FIND!")
                find_next_page.click()
            except:
                break
        print(f"Всего ссылок собрано: {len(all_links)}")

        for link in all_links:
            try:
                driver.get(link)
                time.sleep(2)
                soup = BeautifulSoup(driver.page_source, "html.parser")

                data = {}

                # ID тендера
                try:
                    data["platform_id"] = link.rstrip("/").split("/")[-1]
                except:
                    data["platform_id"] = "--"

                # Ссылка
                try:
                    data["link"] = link
                except:
                    data["link"] = "--"

                # Название
                try:
                    name_tag = soup.select_one("h1.tender-block__title")
                    data["name"] = name_tag.get_text(strip=True) if name_tag else "--"
                except:
                    data["name"] = "--"

                try:
                    type_tag = soup.select_one("div.purchase-type__title")
                    data["selection_method"] = type_tag.get_text(strip=True) if type_tag else "--"
                except:
                    data["selection_method"] = "--"

                # Тип торгов
                try:
                    # Выбираем первый элемент в блоке "purchase-placement"
                    selection_tag = soup.select_one(
                        ".purchase-page__block.tender-block.purchase-placement .tender-named-values_value"
                    )
                    data["type"] = selection_tag.get_text(" ", strip=True) if selection_tag else "--"
                except:
                    data["type"] = "--"

                # Описание
                try:
                    desc_tag = soup.select_one("div.purchase-description__publication-info")
                    data["description"] = desc_tag.get_text(" ", strip=True) if desc_tag else "--"
                except:
                    data["description"] = "--"

                # Организатор
                try:
                    org_tag = soup.select_one("div.lot-customer__info")
                    data["organizer"] = org_tag.get_text(" ", strip=True) if org_tag else "--"
                except:
                    data["organizer"] = "--"

                # Дата публикации
                try:
                    pub_tag = soup.select_one("div.purchase-description__publication-info")
                    if pub_tag:
                        import re
                        match = re.search(r"опубликован\s+([\d\.]+\s[\d:]+)", pub_tag.get_text(" ", strip=True))
                        data["publish_date"] = match.group(1) if match else "--"
                    else:
                        data["publish_date"] = "--"
                except:
                    data["publish_date"] = "--"

                # Дата окончания
                try:
                    date_tag = soup.select_one("span[data-tid='p-date__date']")
                    data["deadline"] = date_tag.get_text(strip=True) if date_tag else "--"
                except Exception:
                    data["deadline"] = "--"

                row = [
                    data["platform_id"],
                    platform_z,
                    data.get("type", "--"),
                    data.get("selection_method", "--"),
                    data["name"],
                    data["description"],
                    data["organizer"],
                    data["link"],
                    data["publish_date"],
                    data["deadline"],
                ]
                try:
                    sheet_kontur.append_rows([row], value_input_option="RAW")
                    print("Сохранено:", row)
                except Exception as e:
                    print("ERROR APPENDING ROW:", e)

            except Exception as e:
                print(f"ERROR GETTING DATA FOR LINK {link}: {e}")

    finally:
        # обязательно закрываем браузер
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    init_driver()
