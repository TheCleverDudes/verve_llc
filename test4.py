import requests
from datetime import datetime, timedelta
import urllib3
import json

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
SALE_ID_TO_FIND = "a9d50607-ed0d-470f-a294-56c66bc4694c"   # 🔁 Replace with target SaleID
PAGE_SIZE = 100
MAX_DAYS_BACK = 30

# === DATE RANGE FOR SEARCH ===
to_date = datetime.today()
from_date = to_date - timedelta(days=MAX_DAYS_BACK)
from_str = from_date.strftime("%Y-%m-%d")
to_str = to_date.strftime("%Y-%m-%d")

# === STEP 1: Find Sale in /SaleList ===
page = 1
target_sale = None # This will hold the summary sale object from /SalesList

print(f"Searching for sale ID: {SALE_ID_TO_FIND}")
while True:
    params = {
        "Page": page,
        "Limit": PAGE_SIZE,
        "from": f"{from_str}T00:00:00",
        "to": f"{to_str}T23:59:59"
    }
    response = requests.get(f"{API_BASE_URL}/salelist", headers=HEADERS, params=params, verify=False)

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP error fetching /salelist on page {page}: {e}")
        print(f"Response content: {response.text}")
        exit()

    sales = response.json().get("SaleList", [])

    if not sales:
        print("No more sales found. Sale not in date range or doesn't exist.")
        break

    for sale in sales:
        if sale.get("ID") == SALE_ID_TO_FIND or sale.get("SaleID") == SALE_ID_TO_FIND:
            target_sale = sale
            break

    if target_sale:
        print(f"[FOUND] Sale found on page {page}")
        break

    page += 1

if not target_sale:
    print(f"[ERROR] Sale {SALE_ID_TO_FIND} not found in the last {MAX_DAYS_BACK} days.")
    exit()

# === STEP 2: Get OrderDate and Customer Info from target_sale (from /SalesList) ===
# The OrderDate from /SalesList is what we want to transfer to SaleOrderDate
original_order_date = target_sale.get("OrderDate")
if not original_order_date:
    print(f"[SKIP] Sale found but has no OrderDate in SaleList data.")
    exit()
print(f"[INFO] Original OrderDate from SalesList: {original_order_date}")

# Get CustomerID or Customer from the target_sale (from /SalesList)
customer_id_from_list = target_sale.get("CustomerID")
customer_name_from_list = target_sale.get("Customer") # Or CustomerName, check your exact /SalesList response

if not customer_id_from_list and not customer_name_from_list:
    print(f"[ERROR] Could not find CustomerID or Customer Name in /SalesList response for Sale {SALE_ID_TO_FIND}.")
    print(f"Full target_sale from /SalesList: {json.dumps(target_sale, indent=2)}")
    exit()

print(f"[INFO] CustomerID from SalesList: {customer_id_from_list}")
print(f"[INFO] Customer Name from SalesList: {customer_name_from_list}")


# === STEP 3: GET the Full Editable Record using /sale/order ===
print("[INFO] Fetching full sale record for update using /sale/order...")
try:
    response = requests.get(
        f"{API_BASE_URL}/sale/order",
        headers=HEADERS,
        params={"SaleID": SALE_ID_TO_FIND},
        verify=False
    )
    response.raise_for_status()

    response_json = response.json()
    sale_data = response_json # This is the full sale object

    if not sale_data.get("SaleID"):
        print("[ERROR] Sale object missing required 'SaleID' field after fetching full record.")
        print(json.dumps(sale_data, indent=2))
        exit()

except requests.exceptions.HTTPError as e:
    print(f"[ERROR] HTTP error fetching full sale record: {e}")
    print(f"Response status code: {response.status_code}")
    print(f"Response content: {response.text}")
    exit()
except json.JSONDecodeError as e:
    print(f"[ERROR] Failed to decode JSON from full sale record response: {e}")
    print(f"Response content (might not be JSON): {response.text}")
    exit()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] A request error occurred fetching full sale record: {e}")
    exit()

# === STEP 4: Inject OrderDate into SaleOrderDate and Customer Info into sale_data ===
# The API docs show 'SaleOrderDate' at the top level, so use that.
sale_data["SaleOrderDate"] = original_order_date
print(f"[INFO] Set 'SaleOrderDate' to: {original_order_date}")

# Inject CustomerID or Customer Name if they are missing from sale_data
# We prefer CustomerID if available, as it's more precise.
if customer_id_from_list and not sale_data.get("CustomerID"):
    sale_data["CustomerID"] = customer_id_from_list
    print(f"[INFO] Injected CustomerID '{customer_id_from_list}' from SalesList.")
elif customer_name_from_list and not sale_data.get("Customer"):
    sale_data["Customer"] = customer_name_from_list
    print(f"[INFO] Injected Customer Name '{customer_name_from_list}' from SalesList.")
else:
    print("[INFO] CustomerID/Customer Name already present in sale_data or not available from SalesList.")

# Initialize AdditionalAttributes as a dictionary if it doesn't exist
# This ensures it's always a dictionary as per API docs example, even if empty.
if "AdditionalAttributes" not in sale_data or not isinstance(sale_data["AdditionalAttributes"], dict):
    sale_data["AdditionalAttributes"] = {}

# If you specifically want to update one of the AdditionalAttributeX fields:
# For example, if "OrderDate" in your UI maps to "AdditionalAttribute1":
# sale_data["AdditionalAttributes"]["AdditionalAttribute1"] = original_order_date
# print(f"[INFO] Injected OrderDate into AdditionalAttributes.AdditionalAttribute1.")
# If you don't need to put it in AdditionalAttributes, you can remove these lines.
print("[INFO] AdditionalAttributes were not explicitly modified for OrderDate based on new API insight.")


# === STEP 5: PUT Updated Sale ===
print("[INFO] Attempting to update sale...")

# Add the 'ID' field for the PUT request, as required by the API.
sale_data["ID"] = SALE_ID_TO_FIND

# DEBUG print to show the *relevant parts* of the payload being sent
print(f"[DEBUG] Full Sale data prepared for PUT (showing key fields):")
debug_payload = {
    "ID": sale_data.get("ID"),
    "SaleID": sale_data.get("SaleID"),
    "SaleOrderNumber": sale_data.get("SaleOrderNumber"), # Added for context
    "SaleOrderDate": sale_data.get("SaleOrderDate"), # Crucial new field
    "CustomerID": sale_data.get("CustomerID"),
    "Customer": sale_data.get("Customer"),
    "AdditionalAttributes": sale_data.get("AdditionalAttributes"),
    "Status": sale_data.get("Status"),
    "Lines_Count": len(sale_data.get("Lines", [])) # Showing if lines are still there
}
print(json.dumps(debug_payload, indent=2))
print("...(Full sale_data object, including all other fields from GET, is sent in PUT request)")


put_response = requests.put(
    f"{API_BASE_URL}/sale",
    headers=HEADERS,
    json=sale_data, # This is the full, modified sale_data
    verify=False
)

try:
    put_response.raise_for_status() # Raise an exception for HTTP errors on PUT
    if put_response.status_code == 200:
        print(f"[SUCCESS] Sale {SALE_ID_TO_FIND} updated successfully with SaleOrderDate = {original_order_date}")
    else:
        print(f"[INFO] PUT request returned status {put_response.status_code}.")
        print(f"Response: {put_response.text}")
except requests.exceptions.HTTPError as e:
    print(f"[ERROR] Failed to update sale: {e}")
    print(f"Response status code: {put_response.status_code}")
    print(f"Response: {put_response.text}")
    exit()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] An error occurred during the PUT request: {e}")
    exit()