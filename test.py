import requests
import json # Import json for pretty printing if needed

# Suppress the InsecureRequestWarning when verify=False is used
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CONFIGURE ===
API_BASE_URL = "https://inventory.dearsystems.com/ExternalApi/v2"
API_KEY = "413a322a-f785-198b-77d5-9f823053ff60" # Replace with your Dear API key
ACCOUNT_ID = "89c7783c-b5fc-4c19-912d-ea89c4c4e8ab" # Replace with your Dear Account ID

HEADERS = {
    "api-auth-accountid": ACCOUNT_ID,
    "api-auth-applicationkey": API_KEY,
    "Content-Type": "application/json"
}

# === TARGET SALE ID ===
sale_id = "a9d50607-ed0d-470f-a294-56c66bc4694c"

# === PAGINATION PARAMETERS ===
PAGE_SIZE = 40 # Or 100, check Dear Systems API documentation for max limit
               # A higher limit reduces the number of requests but increases response size.

# === STEP 1: GET THE SALE from /SalesList with Pagination ===
get_list_url = f"{API_BASE_URL}/salelist"
found_sale_in_list = False
page = 1
target_sale = None

print(f"Attempting to fetch sales list from: {get_list_url}")

while True:
    params = {
        "Page": page,
        "Limit": PAGE_SIZE
    }
    print(f"Fetching page {page} with limit {PAGE_SIZE}...")

    try:
        response = requests.get(get_list_url, headers=HEADERS, params=params, verify=False)
        response.raise_for_status()

        if 'application/json' not in response.headers.get('Content-Type', ''):
            print(f"[ERROR] Expected JSON response, but received Content-Type: {response.headers.get('Content-Type')}")
            print(f"[ERROR] Response text: {response.text}")
            exit()

        sales_list_data = response.json()
        sales_on_page = sales_list_data.get("SaleList", [])

        if not sales_on_page:
            print(f"No more sales found on page {page}. End of pagination.")
            break # No more sales, exit the loop

        # Iterate through the sales on the current page
        for sale in sales_on_page:
            if sale.get("ID") == sale_id:
                target_sale = sale
                found_sale_in_list = True
                print(f"[INFO] Sale {sale_id} found on page {page}.")
                break # Found the sale, exit inner loop

        if found_sale_in_list:
            break # Found the sale, exit outer pagination loop

        # If not found on this page, increment page and continue
        page += 1

    except requests.exceptions.HTTPError as errh:
        print(f"[ERROR] HTTP Error occurred fetching page {page}: {errh}")
        print(f"[ERROR] Response status code: {response.status_code}")
        print(f"[ERROR] Response text: {response.text}")
        exit()
    except requests.exceptions.ConnectionError as errc:
        print(f"[ERROR] Error Connecting: {errc}")
        exit()
    except requests.exceptions.Timeout as errt:
        print(f"[ERROR] Timeout Error: {errt}")
        exit()
    except requests.exceptions.RequestException as err:
        print(f"[ERROR] Something unexpected happened during the request for page {page}: {err}")
        exit()
    except ValueError as e:
        print(f"[ERROR] Failed to decode JSON from response for page {page}: {e}")
        print(f"[ERROR] Response status code: {response.status_code}")
        print(f"[ERROR] Response text (might not be JSON): {response.text}")
        exit()


if not target_sale:
    print(f"[ERROR] Sale {sale_id} not found in SalesList after checking all available pages.")
    exit()

original_order_date = target_sale.get("OrderDate")
if not original_order_date:
    print(f"[SKIP] Sale {sale_id} has no OrderDate in SalesList. This should not happen if the sale exists with an order date.")
    exit()

# === STEP 2: GET THE FULL SALE DETAILS USING /sale/order ===
get_single_sale_url = f"{API_BASE_URL}/sale/order"
print(f"Attempting to fetch full sale details from: {get_single_sale_url} for SaleID: {sale_id}")

try:
    single_sale_response = requests.get(get_single_sale_url, headers=HEADERS, params={"SaleID": sale_id}, verify=False)
    single_sale_response.raise_for_status()

    if 'application/json' not in single_sale_response.headers.get('Content-Type', ''):
        print(f"[ERROR] Expected JSON response for single sale, but received Content-Type: {single_sale_response.headers.get('Content-Type')}")
        print(f"[ERROR] Response text: {single_sale_response.text}")
        exit()

    sale_data = single_sale_response.json()

except requests.exceptions.HTTPError as errh:
    print(f"[ERROR] HTTP Error occurred fetching single sale: {errh}")
    print(f"[ERROR] Response status code: {single_sale_response.status_code}")
    print(f"[ERROR] Response text: {single_sale_response.text}")
    exit()
except ValueError as e:
    print(f"[ERROR] Failed to decode JSON from single sale response: {e}")
    print(f"[ERROR] Response status code: {single_sale_response.status_code}")
    print(f"[ERROR] Response text (might not be JSON): {single_sale_response.text}")
    exit()
except requests.exceptions.RequestException as err:
    print(f"[ERROR] An error occurred fetching single sale: {err}")
    exit()


# === STEP 3: COPY ORDER DATE TO ADDITIONAL ATTRIBUTES ===
if "AdditionalAttributes" not in sale_data or not isinstance(sale_data["AdditionalAttributes"], dict):
    sale_data["AdditionalAttributes"] = {}

sale_data["AdditionalAttributes"]["OrderDate"] = original_order_date
print(f"Set AdditionalAttributes.OrderDate to: {sale_data['AdditionalAttributes']['OrderDate']}")

# === STEP 4: PUT BACK THE UPDATED SALE ===
put_url = f"{API_BASE_URL}/sale"
print(f"Attempting to update sale {sale_id} at: {put_url}")

try:
    put_response = requests.put(put_url, headers=HEADERS, json=sale_data, verify=False)
    put_response.raise_for_status()

    if put_response.status_code == 200:
        print(f"[SUCCESS] Updated Sale {sale_id} with OrderDate = {original_order_date} in AdditionalAttributes.")
    else:
        print(f"[INFO] PUT request returned status {put_response.status_code}, but no error was raised.")
        print(f"[INFO] Response text: {put_response.text}")

except requests.exceptions.HTTPError as errh:
    print(f"[ERROR] HTTP Error occurred during update: {errh}")
    print(f"[ERROR] Response status code: {put_response.status_code}")
    print(f"[ERROR] Response text: {put_response.text}")
    exit()
except requests.exceptions.RequestException as err:
    print(f"[ERROR] An error occurred during update: {err}")
    exit()