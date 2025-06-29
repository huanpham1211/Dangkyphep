from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from streamlit_app import STREAMLIT_APPS
import datetime
import tempfile
import shutil

# ✅ Create a clean temporary directory for Chrome session
temp_dir = tempfile.mkdtemp()

options = Options()
options.binary_location = "/usr/bin/chromium-browser"
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument(f'--user-data-dir={temp_dir}')  # ← KEY FIX

driver = webdriver.Chrome(options=options)

with open("wakeup_log.txt", "a") as log_file:
    log_file.write(f"Execution started at: {datetime.datetime.utcnow()} UTC\n")

    for url in STREAMLIT_APPS:
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            try:
                button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//button[text()='Yes, get this app back up!']"))
                )
                button.click()
                log_file.write(f"[{datetime.datetime.utcnow()}] ✅ Woke up app: {url}\n")
            except TimeoutException:
                log_file.write(f"[{datetime.datetime.utcnow()}] ℹ️ No wake-up button at: {url} (already running?)\n")

        except Exception as e:
            log_file.write(f"[{datetime.datetime.utcnow()}] ❌ Error for {url}: {e}\n")

driver.quit()

# ✅ Clean up temporary Chrome profile directory
shutil.rmtree(temp_dir, ignore_errors=True)
