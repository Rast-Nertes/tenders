import os

from dotenv import load_dotenv

load_dotenv()
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH")

ZAKUP_KONTUR_LOGIN = os.getenv("ZAKUP_KONTUR_LOGIN")
ZAKUP_KONTUR_PASS = os.getenv("ZAKUP_KONTUR_PASS")

B2B_LOGIN = os.getenv("B2B_LOGIN")
B2B_PASSWORD = os.getenv("B2B_PASSWORD")