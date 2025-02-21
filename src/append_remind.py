import requests
import base64
import json

# GitHub 账户和仓库信息
OWNER = 'zhgj'
REPO = 'zhgj.github.io'
FILE_PATH = 'remind.csv'
BRANCH = 'main'

# GitHub API 基础 URL
GITHUB_API_URL = 'https://api.github.com'

# GitHub 访问令牌（需要替换为你的 token）
TOKEN = 'your_github_token'

# 1. 获取文件的 sha 值和 content
def get_file_sha_and_content():
    url = f"{GITHUB_API_URL}/repos/{OWNER}/{REPO}/contents/{FILE_PATH}?ref={BRANCH}"
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print("File got successfully!")
        file_data = response.json()
        # 解码文件内容（Base64解码）
        content = base64.b64decode(file_data['content']).decode('utf-8')
        return file_data['sha'], content
    else:
        print(f"Error fetching file sha and content: {response.status_code}, {response.text}")
        return None

# 2. 提交文件的新内容
def update_file_content(new_content, sha):
    url = f"{GITHUB_API_URL}/repos/{OWNER}/{REPO}/contents/{FILE_PATH}"
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }

    # 编码新的文件内容为Base64
    encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')

    data = {
        'message': 'Add a new line to remind.csv',
        'content': encoded_content,
        'sha': sha,
        'branch': BRANCH
    }

    response = requests.put(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        print("File updated successfully!")
    else:
        print(f"Error updating file: {response.status_code}, {response.text}")

# 3. 主函数，用于测试
def main():
    # 获取当前文件的 sha 和 content
    sha_and_content = get_file_sha_and_content()
    if sha_and_content is None:
        return
    if not sha_and_content[0] or not sha_and_content[1]:
        return

    # 在文件末尾添加新的一行
    new_line = u"提醒6,这是第六条提醒,2025-01-18 01:15:00,未发送\r\n"
    print(sha_and_content[1])

    new_content = sha_and_content[1] + new_line
    print(new_content)

    # 更新文件
    update_file_content(new_content, sha_and_content[0])

if __name__ == '__main__':
    main()
