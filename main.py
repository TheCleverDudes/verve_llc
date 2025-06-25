import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

API_BASE_URL = "https://inventory.dearsystems.com/ExternalApi/v2"
API_KEY = os.getenv("DEAR_API_KEY")
ACCOUNT_ID = os.getenv("DEAR_ACCOUNT_ID")

if not API_KEY or not ACCOUNT_ID:
    raise ValueError("Missing required environment variables: DEAR_API_KEY and DEAR_ACCOUNT_ID")

HEADERS = {
    "api-auth-accountid": ACCOUNT_ID,
    "api-auth-applicationkey": API_KEY,
    "Content-Type": "application/json"
}

PAGE_SIZE = 100

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
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to fetch sale list on page {page}: {response.text}")
            return all_extracted_details if all_extracted_details else []

        sales_from_list = response.json().get("SaleList", [])
        
        if not sales_from_list:
            print(f"  No more sales found on page {page}. End of pagination.")
            break

        for sale in sales_from_list:
            if "SaleID" in sale:
                all_extracted_details.append({
                    "SaleID": sale["SaleID"],
                    "OrderDate": sale.get("OrderDate"),
                    "CustomerID": sale.get("CustomerID"),
                    "Customer": sale.get("Customer"),
                    "OrderNumber": sale.get("OrderNumber")
                })
        page += 1
    
    return all_extracted_details

def update_order_date_for_sale(essential_sale_details):
    sale_id = essential_sale_details["SaleID"]
    order_number = essential_sale_details.get("OrderNumber", "N/A")
    
    try:
        get_url = f"{API_BASE_URL}/sale/order?SaleID={sale_id}"
        print(f"[INFO] Processing SaleID: {sale_id}, OrderNumber: {order_number}")
        print(f"  Fetching full sale record for update from: {get_url}")
        
        response = requests.get(get_url, headers=HEADERS, verify=False)
        if response.status_code != 200:
            print(f"[ERROR] GET sale {sale_id} failed: {response.status_code} - {response.text}")
            return

        detailed_sale_data = response.json()

        # --- Check if AdditionalAttribute2 already has a value ---
        # Get the current value of AdditionalAttribute2
        current_additional_attributes = detailed_sale_data.get("AdditionalAttributes", {})
        current_attr2_value = current_additional_attributes.get("AdditionalAttribute2")

        # Check if it's not None and not an empty string (or any other value you consider 'blank')
        if current_attr2_value and str(current_attr2_value).strip() != "":
            print(f"  [SKIP] AdditionalAttribute2 for Sale {sale_id} already has value '{current_attr2_value}'. Skipping update.")
            return # Skip the rest of the function for this order
        # --- End of skip check ---
        
        sale_data_for_put = {**essential_sale_details, **detailed_sale_data}

        if "ID" not in sale_data_for_put and "SaleID" in sale_data_for_put:
            sale_data_for_put["ID"] = sale_data_for_put["SaleID"]
        elif "ID" not in sale_data_for_put and "SaleID" not in sale_data_for_put:
            print(f"[ERROR] Sale {sale_id} data missing both 'ID' and 'SaleID' for PUT request after merging.")
            return

        if "CustomerID" not in sale_data_for_put and "Customer" not in sale_data_for_put:
            print(f"[ERROR] Sale {sale_id} data missing 'CustomerID' or 'Customer' even after merging for PUT request.")
            return

        original_order_date_full_str = essential_sale_details.get("OrderDate")

        formatted_date_for_attr = None
        if original_order_date_full_str:
            date_part_str = original_order_date_full_str.split('T')[0]
            
            try:
                dt_obj = datetime.strptime(date_part_str, "%Y-%m-%d")
                formatted_date_for_attr = dt_obj.strftime("%m/%d/%Y")
                print(f"  OrderDate from SaleList: {original_order_date_full_str}. Formatted for attribute: {formatted_date_for_attr}")
            except ValueError:
                print(f"  [WARNING] Could not parse date '{date_part_str}'. Falling back to default format.")
                formatted_date_for_attr = date_part_str
        
        if not formatted_date_for_attr:
            formatted_date_for_attr = datetime.now().strftime("%m/%d/%Y")
            print(f"  [INFO] Sale {sale_id} has no valid OrderDate in SaleList. Using current formatted date: {formatted_date_for_attr}")

        if "AdditionalAttributes" not in sale_data_for_put or sale_data_for_put["AdditionalAttributes"] is None:
            sale_data_for_put["AdditionalAttributes"] = {}
        
        if not isinstance(sale_data_for_put["AdditionalAttributes"], dict):
            print(f"  [WARNING] AdditionalAttributes for sale {sale_id} is not a dictionary. Overwriting.")
            sale_data_for_put["AdditionalAttributes"] = {}

        sale_data_for_put["AdditionalAttributes"]["AdditionalAttribute2"] = formatted_date_for_attr
        print(f"  Set 'AdditionalAttributes.AdditionalAttribute2' to: {sale_data_for_put['AdditionalAttributes']['AdditionalAttribute2']}")

        put_url = f"{API_BASE_URL}/sale"
        print(f"  Attempting to update sale {sale_id} via PUT...")
        put_response = requests.put(put_url, headers=HEADERS, json=sale_data_for_put, verify=False)

        if put_response.status_code == 200:
            print(f"[SUCCESS] Sale {sale_id} (Order {order_number}) updated with date {formatted_date_for_attr} in AdditionalAttribute2.")
        else:
            print(f"[ERROR] PUT sale {sale_id} (Order {order_number}) failed: {put_response.status_code} - {put_response.text}")
            print(f"  DEBUG: Payload sent for {sale_id}:\n{json.dumps(sale_data_for_put, indent=2)}")
    except Exception as e:
        print(f"[EXCEPTION] Sale {sale_id} (Order {order_number}) failed: {e}")

if __name__ == "__main__":
    today = datetime.today()
    from_str = today.strftime("%Y-%m-%d")
    to_str = today.strftime("%Y-%m-%d")

    print(f"Starting script to process sales for today: {from_str}...")

    sale_details_to_process = get_recent_sale_details(from_str, to_str)
    print(f"\nFound {len(sale_details_to_process)} sales from today's date.")

    if not sale_details_to_process:
        print("No sales to process for today. Exiting.")
    else:
        for sale_detail in sale_details_to_process:
            update_order_date_for_sale(sale_detail)

    print("\nScript finished.")