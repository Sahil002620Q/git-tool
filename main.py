import os
import requests
import json
from dotenv import load_dotenv

# Load settings
load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN")
CONFIG_FILE = "config.json"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def manage_ignore_list():
    while True: 
        config = load_config()
        clear_screen()
        print("=== MANAGE IGNORE LIST ===")
        print(f"Ignored: {', '.join(config['ignore_list'])}")
        print("-" * 30)
        print("1. Add user")
        print("2. Remove user")
        print("3. Back to Main Menu")
        
        choice = input("\nSelect: ")
        
        if choice == '1':
            user = input("Enter GitHub username to ignore: ").strip()
            if user and user not in config['ignore_list']:
                config['ignore_list'].append(user)
                save_config(config)
        elif choice == '2':
            user = input("Enter GitHub username to remove: ").strip()
            if user and user in config['ignore_list']:
                config['ignore_list'].remove(user)
                save_config(config)
        elif choice == '3':
            break
    

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"username": "", "ignore_list": []}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_github_data(endpoint, username):
    items = []
    page = 1
    headers = {"Authorization": f"token {TOKEN}"} if TOKEN else {}
    while True:
        url = f"https://api.github.com/users/{username}/{endpoint}?per_page=100&page={page}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200 or not response.json():
            break
        items.extend([u['login'] for u in response.json()])
        page += 1
    return set(items)

def main():
    config = load_config()
    ignore_set = set(config.get('ignore_list', []))
    while True:
        clear_screen()
        print("=== GITHUB UNFOLLOWER CLI ===")
        print(f"User: {config.get('username', 'Not Set')}")
        print("-" * 30)
        print("1. View Non-Followers")
        print("2. Manage Ignore List")
        print("3. Change Username")
        print("4. Exit")
        
        choice = input("\nSelect an option: ")
        
        if choice == '1':
            if not config.get('username'):
                input("Username not set. Press Enter to return.")
                continue
            
            print("\nFetching data, please wait...")
            following = get_github_data("following", config['username'])
            followers = get_github_data("followers", config['username'])
            
            ignore_set = set(config.get('ignore_list', []))
            not_following = sorted(list((following - followers) - ignore_set))
            
            clear_screen()
            print(f"=== USERS NOT FOLLOWING YOU BACK ({len(not_following)}) ===")
            if not_following:
                print(f"(Loaded ignore list: {sorted(ignore_set)})")
            if not not_following:
                print("Everyone is following you back!")
            else:
                for i, user in enumerate(not_following):
                    print(f"  {i+1:02d}. {user}")
                
                idx = input("\n[Enter number to unfollow] or [Enter to return]: ")
                if idx.isdigit() and 1 <= int(idx) <= len(not_following):
                    target = not_following[int(idx)-1]
                    # You can add the unfollow call here
                    print(f"\nProcessing unfollow for {target}...")
                    # ... [unfollow logic]
            input("\nPress Enter to return to menu...")
            
        elif choice == '2':
            manage_ignore_list()
            # reload config so ignore list changes apply immediately
            config = load_config()
            ignore_set = set(config.get('ignore_list', []))
        elif choice == '4':
            break

if __name__ == "__main__":
    main()
