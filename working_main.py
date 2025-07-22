import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import json
import urllib3
import time # For rate limiting

# Suppress SSL warnings (useful for development, but consider proper SSL certs in production)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables from .env file
load_dotenv()

# === CONFIGURATION ===
API_BASE_URL = "https://inventory.dearsystems.com/ExternalApi/v2"
API_KEY = os.getenv("DEAR_API_KEY")      # Load from environment variables
ACCOUNT_ID = os.getenv("DEAR_ACCOUNT_ID")    # Load from environment variables

if not API_KEY or not ACCOUNT_ID:
    raise ValueError("Missing required environment variables: DEAR_API_KEY and DEAR_ACCOUNT_ID")

HEADERS = {
    "api-auth-accountid": ACCOUNT_ID,
    "api-auth-applicationkey": API_KEY,
    "Content-Type": "application/json"
}

# === API RATE LIMITING SETTINGS ===
# Dear Systems API limit is 60 calls per 60 seconds.
# We'll put a small delay after each call to stay well within limits.
# 1.1 seconds means max ~54 calls/minute
API_CALL_DELAY_SECONDS = 1.1 

# === PAGINATION SETTING ===
PAGE_SIZE = 100 # Maximum items per page as allowed by Dear API

# === STEP 1: GET ALL SALE IDS (and essential details) with Pagination ===
def get_recent_sale_details(from_date_str, to_date_str):
    url = f"{API_BASE_URL}/salelist"
    all_extracted_details = []
    page = 1

    print(f"Fetching sales from {from_date_str} to {to_date_str} with pagination...")

    while True:
        params = {
            "FromDate": from_date_str,
            "ToDate": to_date_str,
            "Page": page,
            "Limit": PAGE_SIZE
        }
        
        print(f"  Fetching page {page} with limit {PAGE_SIZE}...")
        response = requests.get(url, headers=HEADERS, params=params, verify=False)
        
        # This sleep is crucial: it ensures there's a delay AFTER each page fetch
        time.sleep(API_CALL_DELAY_SECONDS) 

        if response.status_code != 200:
            print(f"[ERROR] Failed to fetch sale list on page {page}: {response.text}")
            # If an error occurs, we return what we've collected so far, or an empty list if it's the first page
            return all_extracted_details if all_extracted_details else []

        sales_from_list = response.json().get("SaleList", [])
        
        if not sales_from_list:
            print(f"  No more sales found on page {page}. End of pagination.")
            break # No more sales, exit the loop

        for sale in sales_from_list:
            if "SaleID" in sale:
                all_extracted_details.append({
                    "SaleID": sale["SaleID"],
                    "OrderDate": sale.get("OrderDate"), # Use .get() in case it's missing
                    "CustomerID": sale.get("CustomerID"),
                    "Customer": sale.get("Customer"),
                    "OrderNumber": sale.get("OrderNumber") # Also useful for logging/identifying
                })
        page += 1
    
    return all_extracted_details

# === STEP 2: UPDATE AdditionalAttributes.OrderDate ===
def update_order_date_for_sale(essential_sale_details):
    sale_id = essential_sale_details["SaleID"]
    order_number = essential_sale_details.get("OrderNumber", "N/A")
    
    try:
        get_url = f"{API_BASE_URL}/sale/order?SaleID={sale_id}"
        print(f"[INFO] Processing SaleID: {sale_id}, OrderNumber: {order_number}")
        print(f"  Fetching full sale record for update from: {get_url}")
        
        response = requests.get(get_url, headers=HEADERS, verify=False)
        
        # Delay after fetching individual sale record
        time.sleep(API_CALL_DELAY_SECONDS) 

        if response.status_code != 200:
            print(f"[ERROR] GET sale {sale_id} failed: {response.status_code} - {response.text}")
            return

        detailed_sale_data = response.json()

        # --- DEBUG: Print the full detailed_sale_data to inspect AdditionalAttributes ---
        # Comment this out for production runs to reduce log verbosity
        # print(f"  [DEBUG] Full detailed_sale_data for {sale_id}:\n{json.dumps(detailed_sale_data, indent=2)}")
        # --- END DEBUG ---

        # --- More robust skip check for AdditionalAttribute2 ---
        # 1. Check if 'AdditionalAttributes' key exists and is a dictionary
        if "AdditionalAttributes" in detailed_sale_data and \
           isinstance(detailed_sale_data["AdditionalAttributes"], dict):
            
            # 2. Then, safely get 'AdditionalAttribute2' value
            current_attr2_value = detailed_sale_data["AdditionalAttributes"].get("AdditionalAttribute2")

            # 3. Check if the value is not None AND not an empty string (after stripping whitespace)
            if current_attr2_value is not None and str(current_attr2_value).strip() != "":
                print(f"  [SKIP] AdditionalAttribute2 for Sale {sale_id} already has value '{current_attr2_value}'. Skipping update.")
                return # Skip the rest of the function for this order
        
        # If 'AdditionalAttributes' key is missing, or not a dict, or 'AdditionalAttribute2' is empty/None,
        # the code will continue past this 'if' block.
        # --- End of robust skip check ---
        
        # Combine essential details from SaleList with detailed_sale_data
        sale_data_for_put = {**essential_sale_details, **detailed_sale_data}

        # Ensure the 'ID' field is present for the PUT request
        if "ID" not in sale_data_for_put and "SaleID" in sale_data_for_put:
            sale_data_for_put["ID"] = sale_data_for_put["SaleID"]
        elif "ID" not in sale_data_for_put and "SaleID" not in sale_data_for_put:
            print(f"[ERROR] Sale {sale_id} data missing both 'ID' and 'SaleID' for PUT request after merging.")
            return

        # Ensure CustomerID or Customer name is present (critical for PUT requests)
        if "CustomerID" not in sale_data_for_put and "Customer" not in sale_data_for_put:
            print(f"[ERROR] Sale {sale_id} data missing 'CustomerID' or 'Customer' even after merging for PUT request.")
            return

        # Get OrderDate from the essential details and reformat it to MM/DD/YYYY
        original_order_date_full_str = essential_sale_details.get("OrderDate")

        formatted_date_for_attr = None
        if original_order_date_full_str:
            date_part_str = original_order_date_full_str.split('T')[0] # e.g., "2025-06-19"
            
            try:
                dt_obj = datetime.strptime(date_part_str, "%Y-%m-%d")
                formatted_date_for_attr = dt_obj.strftime("%m/%d/%Y") # Format to MM/DD/YYYY
                print(f"  OrderDate from SaleList: {original_order_date_full_str}. Formatted for attribute: {formatted_date_for_attr}")
            except ValueError:
                print(f"  [WARNING] Could not parse date '{date_part_str}'. Falling back to default YYYY-MM-DD format.")
                formatted_date_for_attr = date_part_str # Fallback if parsing fails
        
        if not formatted_date_for_attr: # If original was empty or parsing failed
            # Fallback to current date if OrderDate is unexpectedly missing or couldn't be parsed
            formatted_date_for_attr = datetime.now().strftime("%m/%d/%Y")
            print(f"  [INFO] Sale {sale_id} has no valid OrderDate in SaleList. Using current formatted date: {formatted_date_for_attr}")

        # Ensure AdditionalAttributes exists and is a dictionary before setting
        # This block is somewhat redundant after the skip check, but acts as a final safeguard
        if "AdditionalAttributes" not in sale_data_for_put or sale_data_for_put["AdditionalAttributes"] is None:
            sale_data_for_put["AdditionalAttributes"] = {}
        
        if not isinstance(sale_data_for_put["AdditionalAttributes"], dict):
            print(f"  [WARNING] AdditionalAttributes for sale {sale_id} is not a dictionary. Overwriting.")
            sale_data_for_put["AdditionalAttributes"] = {}

        # Set the date for AdditionalAttribute2 with the MM/DD/YYYY format
        sale_data_for_put["AdditionalAttributes"]["AdditionalAttribute2"] = formatted_date_for_attr
        print(f"  Set 'AdditionalAttributes.AdditionalAttribute2' to: {sale_data_for_put['AdditionalAttributes']['AdditionalAttribute2']}")

        put_url = f"{API_BASE_URL}/sale"
        print(f"  Attempting to update sale {sale_id} via PUT...")
        put_response = requests.put(put_url, headers=HEADERS, json=sale_data_for_put, verify=False)
        
        # Delay after PUT request
        time.sleep(API_CALL_DELAY_SECONDS) 

        if put_response.status_code == 200:
            print(f"[SUCCESS] Sale {sale_id} (Order {order_number}) updated with date {formatted_date_for_attr} in AdditionalAttribute2.")
        else:
            print(f"[ERROR] PUT sale {sale_id} (Order {order_number}) failed: {put_response.status_code} - {put_response.text}")
            print(f"  DEBUG: Payload sent for {sale_id}:\n{json.dumps(sale_data_for_put, indent=2)}")
    except Exception as e:
        print(f"[EXCEPTION] Sale {sale_id} (Order {order_number}) failed: {e}")

# === MAIN EXECUTION ===
if __name__ == "__main__":
    # Date range for SaleList - set to today's date
    today = datetime.today()
    from_str = today.strftime("%Y-%m-%d")
    to_str = today.strftime("%Y-%m-%d")

    print(f"Starting script to process sales for today: {from_str}...")

    # <<< NEW: Add an initial delay BEFORE the very first API call >>>
    # This ensures your first call doesn't hit a limit if the previous minute was active.
    time.sleep(API_CALL_DELAY_SECONDS) 

    # Call the modified get_recent_sale_details with today's date range
    sale_details_to_process = get_recent_sale_details(from_str, to_str)
    print(f"\nFound {len(sale_details_to_process)} sales from today's date.")

    if not sale_details_to_process:
        print("No sales to process for today. Exiting.")
    else:
        for sale_detail in sale_details_to_process:
            update_order_date_for_sale(sale_detail)

    print("\nScript finished.")