import os
import requests
import json
from dotenv import load_dotenv

# Load your token from .env
load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN")

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"username": "", "ignore_list": []}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_github_data(endpoint, username):
    """Fetches all pages from GitHub API."""
    items = []
    page = 1
    headers = {"Authorization": f"token {TOKEN}"} if TOKEN else {}
    
    while True:
        url = f"https://api.github.com/users/{username}/{endpoint}?per_page=100&page={page}"
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.json().get('message')}")
            break
            
        data = response.json()
        if not data:
            break
            
        items.extend([u['login'] for u in data])
        page += 1
    return set(items)

def unfollow_user(username):
    headers = {"Authorization": f"token {TOKEN}"}
    url = f"https://api.github.com/user/following/{username}"
    response = requests.delete(url, headers=headers)
    return response.status_code == 204

def main():
    config = load_config()
    
    while True:
        print("\n--- GitHub Unfollower CLI ---")
        print(f"1. Check Non-Followers (User: {config.get('username', 'Not Set')})")
        print("2. Manage Ignore List")
        print("3. Set Username")
        print("4. Exit")
        
        choice = input("Select: ")
        
        if choice == '1':
            if not config.get('username'):
                print("Error: Set username first.")
                continue
            
            print("Fetching data...")
            following = get_github_data("following", config['username'])
            followers = get_github_data("followers", config['username'])
            
            not_following = following - followers
            # Remove ignored users
            final_list = [u for u in not_following if u not in config['ignore_list']]
            
            if not final_list:
                print("Everyone is following you back!")
            else:
                for i, user in enumerate(sorted(final_list)):
                    print(f"{i+1}. {user}")
                
                cmd = input("\nEnter number to unfollow (or press Enter to back): ")
                if cmd.isdigit() and 1 <= int(cmd) <= len(final_list):
                    target = sorted(final_list)[int(cmd)-1]
                    if unfollow_user(target):
                        print(f"Unfollowed {target}")
                    else:
                        print("Failed. Ensure your GITHUB_TOKEN has 'user:follow' scope.")
        
        elif choice == '2':
            print(f"Ignore List: {config['ignore_list']}")
            act = input("Add (a) or Remove (r) user? ")
            name = input("Username: ")
            if act == 'a':
                config['ignore_list'].append(name)
            elif act == 'r' and name in config['ignore_list']:
                config['ignore_list'].remove(name)
            save_config(config)
            
        elif choice == '3':
            config['username'] = input("Enter your GitHub username: ")
            save_config(config)
            
        elif choice == '4':
            break

if __name__ == "__main__":
    main()
