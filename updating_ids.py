import requests
import json

item_ids = []

page = 1
limit = 25

while True:
    print(f"Fetching page {page}...")
    url = f"https://api.darkerdb.com/v1/items?page={page}&limit={limit}"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"Error fetching data on page {page}. Status code: {response.status_code}")
        break
    
    data = response.json()
    items = data.get("body", [])
    
    if not items:
        print("No more items found, stopping.")
        break
    
    print(f"Extracting {len(items)} items from page {page}...")
    for item in items:
        item_id = item.get("id")
        if item_id:
            print(f"Extracting item id: {item_id}")
            item_ids.append(item_id)
    
    pagination = data.get("pagination", {})
    current_page = pagination.get("page", page)
    total_pages = pagination.get("num_pages", page)
    
    if current_page >= total_pages:
        print("Reached the last page.")
        break
    else:
        page += 1

with open("item_ids.json", "w") as json_file:
    json.dump(item_ids, json_file, indent=4)
print("Item ids have been saved to 'item_ids.json'.")

with open("item_ids.txt", "w") as txt_file:
    for item_id in item_ids:
        txt_file.write(f"{item_id}\n")
print("Item ids have been saved to 'item_ids.txt'.")
