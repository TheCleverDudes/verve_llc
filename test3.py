import requests
from datetime import datetime, timedelta
import urllib3

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CONFIGURATION ===
API_BASE_URL = "https://inventory.dearsystems.com/ExternalApi/v2"
API_KEY = "413a322a-f785-198b-77d5-9f823053ff60" # Replace with your Dear API key
ACCOUNT_ID = "89c7783c-b5fc-4c19-912d-ea89c4c4e8ab" # Replace with your Dear Account ID

HEADERS = {
    "api-auth-accountid": ACCOUNT_ID,
    "api-auth-applicationkey": API_KEY,
    "Content-Type": "application/json"
}

# === SETTINGS ===
SALE_ID_TO_FIND = "a9d50607-ed0d-470f-a294-56c66bc4694c"  # 🔁 Replace with the SaleID to test
PAGE_SIZE = 100
MAX_DAYS_BACK = 30

# === DATE RANGE FOR SEARCH ===
to_date = datetime.today()
from_date = to_date - timedelta(days=MAX_DAYS_BACK)
from_str = from_date.strftime("%Y-%m-%d")
to_str = to_date.strftime("%Y-%m-%d")

# === STEP 1: Find Sale in /SaleList with Pagination ===
page = 1
target_sale = None

print(f"Searching for sale ID: {SALE_ID_TO_FIND}")
while True:
    params = {
        "Page": page,
        "Limit": PAGE_SIZE,
        "from": f"{from_str}T00:00:00",
        "to": f"{to_str}T23:59:59"
    }
    response = requests.get(f"{API_BASE_URL}/salelist", headers=HEADERS, params=params, verify=False)
    response.raise_for_status()
    sales = response.json().get("SaleList", [])

    if not sales:
        print("No more sales found. Sale not in date range or doesn't exist.")
        break

    for sale in sales:
        if sale.get("SaleID") == SALE_ID_TO_FIND:
            target_sale = sale
            break

    if target_sale:
        print(f"[FOUND] Sale found on page {page}")
        break

    page += 1

if not target_sale:
    print(f"[ERROR] Sale {SALE_ID_TO_FIND} not found in the last {MAX_DAYS_BACK} days.")
    exit()

# === STEP 2: Get OrderDate ===
original_order_date = target_sale.get("OrderDate")
if not original_order_date:
    print(f"[SKIP] Sale found but has no OrderDate.")
    exit()
print(f"[INFO] Original OrderDate: {original_order_date}")

# === STEP 3: Get Full Sale Details via /sale ===
print("[INFO] Fetching full sale record for update...")
response = requests.get(
    f"{API_BASE_URL}/sale/order",
    headers=HEADERS,
    params={"SaleID": SALE_ID_TO_FIND},
    verify=False
)
response.raise_for_status()
sale_data = response.json()

# === STEP 4: Inject OrderDate into AdditionalAttributes ===
if "AdditionalAttributes" not in sale_data or not isinstance(sale_data["AdditionalAttributes"], dict):
    sale_data["AdditionalAttributes"] = {}
sale_data["AdditionalAttributes"]["OrderDate"] = original_order_date
print(f"[INFO] Injected OrderDate into AdditionalAttributes.")

# === STEP 5: PUT Updated Sale ===
print("[INFO] Attempting to update sale...")
put_response = requests.put(
    f"{API_BASE_URL}/sale/order",
    headers=HEADERS,
    json=sale_data,
    verify=False
)

if put_response.status_code == 200:
    print(f"[SUCCESS] Sale {SALE_ID_TO_FIND} updated successfully with OrderDate = {original_order_date}")
else:
    print(f"[ERROR] Failed to update sale: {put_response.status_code}")
    print(f"Response: {put_response.text}")
