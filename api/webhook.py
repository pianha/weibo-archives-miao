import os
import json
import base64
import requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            # 预期接收的 JSON 结构:
            # {
            #    "id": "微博ID",
            #    "avatar": "博主头像链接",
            #    "name": "博主昵称",
            #    "created_at": "2026-10-03 12:00:00",
            #    "text": "微博正文内容",
            #    "pics": ["图片1链接", "图片2链接"],
            #    "video": "视频直链（可选，没有则不填）"
            # }
            weibo_id = data.get("id")
            avatar = data.get("avatar", "https://via.placeholder.com/40")
            name = data.get("name", "微博用户")
            created_at = data.get("created_at", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            text = data.get("text", "")
            pics = data.get("pics", [])
            video = data.get("video", "")
            
            # 提取年月用于按月归档，例如 "2026-10"
            year_month = created_at[:7]
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON format")
            return

        # 1. 组装单条微博的高仿卡片 HTML 片段
        pics_html = ""
        if pics:
            grid_class = "wb-media-grid single" if len(pics) == 1 else "wb-media-grid"
            imgs = "".join([f'<img src="{pic}" loading="lazy">' for pic in pics])
            pics_html = f'<div class="{grid_class}">{imgs}</div>'
            
        video_html = f'<video class="wb-video" src="{video}" controls preload="metadata"></video>' if video else ""
        
        single_post_html = f"""
        <div class="wb-card" id="wb-{weibo_id}">
            <div class="wb-header">
                <img src="{avatar}" class="wb-avatar" alt="avatar">
                <div class="wb-info">
                    <div class="wb-name">{name}</div>
                    <div class="wb-time">{created_at}</div>
                </div>
            </div>
            <div class="wb-text">{text}</div>
            {pics_html}
            {video_html}
        </div>
        """

        # 2. 对接 GitHub API 获取该月已有的 HTML 文件
        github_token = os.environ.get("GITHUB_TOKEN")
        repo_owner = os.environ.get("REPO_OWNER")
        repo_name = os.environ.get("REPO_NAME")
        
        file_path = f"archives/{year_month}.html"
        github_api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }
        
        existing_content = ""
        file_sha = None
        
        # 尝试读取远端同月文件
        res = requests.get(github_api_url, headers=headers)
        if res.status_code == 200:
            file_data = res.json()
            file_sha = file_data.get("sha")
            existing_content = base64.b64decode(file_data.get("content")).decode('utf-8')

        # 3. 拼接或创建 HTML
        marker = '<div id="posts-stream">'
        if existing_content:
            # 如果文件已存在，将新帖子插入到原有流的最上方（倒序，最新在最前）
            if marker in existing_content:
                parts = existing_content.split(marker)
                updated_html = parts[0] + marker + "\n" + single_post_html + parts[1]
            else:
                updated_html = existing_content + single_post_html
        else:
            # 首次创建该月的 HTML 模板
            updated_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>微博存档 - {year_month}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f5f5f5; color: #333; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        .month-title {{ font-size: 1.4em; font-weight: bold; margin-bottom: 20px; padding-left: 8px; border-left: 4px solid #ff8200; color: #eb7350; }}
        .wb-card {{ background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .wb-header {{ display: flex; align-items: center; margin-bottom: 12px; }}
        .wb-avatar {{ width: 40px; height: 40px; border-radius: 50%; object-fit: cover; margin-right: 10px; }}
        .wb-info .wb-name {{ font-size: 0.95em; font-weight: bold; color: #333; }}
        .wb-info .wb-time {{ font-size: 0.8em; color: #939393; margin-top: 2px; }}
        .wb-text {{ font-size: 1em; line-height: 1.6; word-break: break-all; white-space: pre-wrap; margin-bottom: 12px; color: #111; }}
        .wb-media-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-bottom: 12px; max-width: 400px; }}
        .wb-media-grid img {{ width: 100%; aspect-ratio: 1/1; object-fit: cover; border-radius: 4px; background: #f0f0f0; }}
        .wb-media-grid.single img {{ max-width: 250px; aspect-ratio: auto; }}
        .wb-video {{ width: 100%; max-height: 400px; border-radius: 6px; background: #000; margin-bottom: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="month-title">📅 {year_month} 存档</div>
        <div id="posts-stream">
            {single_post_html}
        </div>
    </div>
</body>
</html>"""

        # 4. 提交/更新回 GitHub 仓库
        encoded_content = base64.b64encode(updated_html.encode('utf-8')).decode('utf-8')
        payload = {
            "message": f"Auto-append Weibo post {weibo_id} to {year_month}.html",
            "content": encoded_content
        }
        if file_sha:
            payload["sha"] = file_sha

        put_res = requests.put(github_api_url, json=payload, headers=headers)
        
        if put_res.status_code in [200, 201]:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Success: Post appended to monthly HTML!")
        else:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"GitHub Error: {put_res.text}".encode('utf-8'))
