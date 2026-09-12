from flask import Flask, render_template
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
import os

app = Flask(__name__)

def scrape_fomc_data():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Set binary path for Linux (Render) environment
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    # Set driver path for Linux (Render) environment
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://centralbank.watch/federal-reserve/")
        time.sleep(4)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # --- 1. Scrape First Table ---
        banner_text = "Markets price tightening across upcoming meetings."
        banner_sub = "Per-meeting percentages describe the same single expected path."

        for el in soup.find_all(['div', 'section']):
            txt = el.get_text(separator=' ', strip=True)
            if "tightening in total" in txt or "hikes" in txt:
                sentences = [s.strip() for s in txt.split('.') if s.strip()]
                if len(sentences) >= 1:
                    banner_text = sentences[0] + '.'
                if len(sentences) >= 2:
                    banner_sub = sentences[1] + '.'
                break

        meetings = []
        date_pattern = re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', re.IGNORECASE)

        for row in soup.find_all(['tr', 'div']):
            text = row.get_text(separator=' ', strip=True)
            if date_pattern.search(text) and "%" in text:
                match = date_pattern.search(text)
                meeting_date = match.group(0)

                if not any(m['date'] == meeting_date for m in meetings):
                    pcts = re.findall(r'\d+\.\d+%', text)
                    bps = re.findall(r'[+-]?\d+\.?\d*\s*bp', text)
                    rates = re.findall(r'\b[345]\.\d{2}%\b', text)

                    prob_val = pcts[0] if pcts else "0.0%"
                    bp_val = bps[0] if bps else "+0.0 bp"
                    rate_val = rates[0] if rates else "0.00%"

                    higher_match = re.search(r'higher\s*(\d+\.\d+%)', text, re.IGNORECASE)
                    same_match = re.search(r'same\s*(\d+\.\d+%)', text, re.IGNORECASE)
                    lower_match = re.search(r'lower\s*(\d+\.\d+%)', text, re.IGNORECASE)

                    higher_val = f"higher {higher_match.group(1)}" if higher_match else "higher 0.0%"
                    same_val = f"same {same_match.group(1)}" if same_match else "same 0.0%"
                    lower_val = f"lower {lower_match.group(1)}" if lower_match else "lower 0.0%"

                    try:
                        numeric_prob = float(prob_val.replace('%', '').strip())
                    except ValueError:
                        numeric_prob = 50.0

                    meetings.append({
                        "date": meeting_date,
                        "probability": prob_val,
                        "prob_width": f"{min(numeric_prob, 100)}%",
                        "bp": bp_val,
                        "rate": rate_val,
                        "higher": higher_val,
                        "same": same_val,
                        "lower": lower_val
                    })

        # --- 2. Scrape Second Matrix Table ---
        matrix_headers = []
        matrix_rows = []

        tables = soup.find_all('table')
        for table in tables:
            trs = table.find_all('tr')
            if trs:
                header_cells = trs[0].find_all(['th', 'td'])
                header_texts = [c.get_text(strip=True) for c in header_cells]
                # Ensure we find the probability matrix table (contains 'Rate' and meeting columns, avoiding indicator tables)
                if header_texts and header_texts[0].lower() == 'rate' and len(header_texts) > 1:
                    matrix_headers = header_texts
                    for tr in trs[1:]:
                        cols = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
                        if cols:
                            matrix_rows.append(cols)
                    break

        # Fallback if specific table wasn't matched above
        if not matrix_headers:
            for table in tables:
                trs = table.find_all('tr')
                if trs:
                    header_cells = trs[0].find_all(['th', 'td'])
                    header_texts = [c.get_text(strip=True) for c in header_cells]
                    if any('Rate' in h for h in header_texts) and not any('Indicator' in h for h in header_texts):
                        matrix_headers = header_texts
                        for tr in trs[1:]:
                            cols = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
                            if cols:
                                matrix_rows.append(cols)
                        break

        if not matrix_headers:
            matrix_headers = ["Rate", "Sep 26", "Oct 26", "Dec 26"]
            matrix_rows = [
                ["4.38%", "", "", "35"],
                ["4.13%", "", "41", "50"],
                ["3.88%", "85", "51", "14"],
                ["3.63%", "15", "8", "1"]
            ]

        processed_matrix_rows = []
        for row in matrix_rows:
            processed_row = []
            for i, val in enumerate(row):
                if i == 0 or not val:
                    processed_row.append({"val": val, "is_header": i == 0, "bg": "", "color": ""})
                else:
                    try:
                        num = int(val)
                        opacity = num / 100 * 0.8
                        bg = f"rgba(99, 102, 241, {opacity})"
                        color = "#ffffff" if num > 40 else "#1e293b"
                    except ValueError:
                        bg = ""
                        color = ""
                    processed_row.append({"val": val, "is_header": False, "bg": bg, "color": color})
            processed_matrix_rows.append(processed_row)

        return banner_text, banner_sub, meetings, matrix_headers, processed_matrix_rows

    finally:
        driver.quit()

@app.route("/")
def index():
    banner, banner_sub, meetings, matrix_headers, matrix_rows = scrape_fomc_data()
    return render_template("index.html", banner=banner, banner_sub=banner_sub, meetings=meetings, matrix_headers=matrix_headers, matrix_rows=matrix_rows)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)