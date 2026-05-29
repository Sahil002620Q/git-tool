import requests
import os

def get_data(username, endpoint, token):
    headers = {"Authorization": f"token {token}"} if token else {}
    data = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{username}/{endpoint}?per_page=100&page={page}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200 or not response.json():
            break
        data.extend([u['login'] for u in response.json()])
        page += 1
    return set(data)

def unfollow_user(target_user, token):
    headers = {"Authorization": f"token {token}"}
    url = f"https://api.github.com/user/following/{target_user}"
    response = requests.delete(url, headers=headers)
    return response.status_code == 204
