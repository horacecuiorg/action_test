import os
import requests
import json
from datetime import datetime
import sys
import argparse # 导入 argparse 模块

def list_ghcr_image_tags(owner, image_name, github_token, use_auth):
    """
    列出 GHCR 指定镜像的所有标签。
    通过 GitHub REST API v3 调用。
    """
    print(f"查询 GHCR 镜像: {owner}/{image_name}")
    # GHCR API 文档：https://docs.github.com/en/rest/packages/container-images
    # 列出容器包的所有版本 (即标签): GET /users/{username}/packages/{package_type}/{package_name}/versions
    # 对于容器镜像，package_type 是 'container'
    api_url = f"https://api.github.com/users/{owner}/packages/container/{image_name}/versions"
    
    headers = {
        "Accept": "application/vnd.github.v3+json" # 确保接受 GitHub API v3 JSON 格式
    }
    
    if use_auth and github_token:
        headers["Authorization"] = f"token {github_token}" # 使用 Personal Access Token (PAT) 或 GITHUB_TOKEN
    elif use_auth:
        print("警告: 已选择使用认证 (--use-auth 为 true) 但未提供 --github-token 参数，尝试匿名访问（可能受限或失败）。", file=sys.stderr)
        # 即使没有 token，headers 也会保持不变，requests 会尝试匿名访问
    else:
        print("未启用认证 (--use-auth 为 false)，尝试匿名访问（可能受限或失败）。")


    all_tags = []
    page = 1
    # GHCR API 通常没有 'next' 字段，而是通过分页参数（page, per_page）控制
    while True:
        try:
            # 每次请求 100 条记录，GitHub API 的默认和最大值
            response = requests.get(f"{api_url}?page={page}&per_page=100", headers=headers)
            response.raise_for_status() # 如果响应状态码不是 2xx，则抛出 HTTPError 异常
            data = response.json()

            if not data: # 如果响应数据为空，表示没有更多页了
                break
            
            for version in data:
                # GHCR API 返回的是 version 对象，其中包含 metadata 和 container 信息
                metadata = version.get('metadata', {})
                container_metadata = metadata.get('container', {})
                
                tags = container_metadata.get('tags', []) # 镜像的所有标签
                digest = container_metadata.get('digest') # 镜像的摘要 (ID)
                
                # 只有有标签的才加入，或者可以根据需求调整（例如，包括无标签的镜像版本）
                if tags:
                    all_tags.append({
                        'tags': tags,
                        'digest': digest,
                        'created_at': version.get('created_at'),
                        'updated_at': version.get('updated_at')
                    })
            page += 1 # 移动到下一页
        except requests.exceptions.RequestException as e:
            print(f"查询 GHCR API 时出错: {e}", file=sys.stderr)
            print(f"响应状态码: {response.status_code if 'response' in locals() else 'N/A'}", file=sys.stderr)
            print(f"响应内容: {response.text if 'response' in locals() else 'N/A'}", file=sys.stderr)
            break # 发生错误时退出循环
    
    print(f"找到 {len(all_tags)} 个 GHCR 镜像标签。")
    return all_tags

def main():
    # 初始化 ArgumentParser 来处理命令行参数
    parser = argparse.ArgumentParser(description="List GitHub Container Registry (GHCR) image tags.")
    parser.add_argument('--owner', type=str, required=True,
                        help='GitHub username or organization name (GHCR owner).')
    parser.add_argument('--image-name', type=str, required=True,
                        help='GHCR image name to query.')
    parser.add_argument('--use-auth', type=lambda x: x.lower() == 'true', default=False,
                        help='Whether to use GitHub Token for authentication (true/false).')
    parser.add_argument('--github-token', type=str, default='',
                        help='GitHub Personal Access Token (PAT) or GITHUB_TOKEN (required if --use-auth is true).')
    
    args = parser.parse_args() # 解析命令行参数

    owner = args.owner
    image_name = args.image_name
    use_auth = args.use_auth
    github_token = args.github_token

    # 参数校验
    if not owner or not image_name:
        print("错误: 必须为 GHCR 指定 --owner 和 --image-name 参数。", file=sys.stderr)
        sys.exit(1)
    
    if use_auth and not github_token:
        print("错误: 当 --use-auth 为 true 时，必须提供 --github-token。", file=sys.stderr)
        sys.exit(1)
    
    results = {}
    # 调用核心函数获取 GHCR 镜像标签
    tags_list = list_ghcr_image_tags(
        owner=owner, 
        image_name=image_name, 
        github_token=github_token, 
        use_auth=use_auth
    )
    results['ghcr_image_tags'] = tags_list

    # --- 将 JSON 输出写入文件并设置 GitHub Actions 输出 ---
    output_json_path = "ghcr_results.json" # 定义输出 JSON 文件名
    with open(output_json_path, 'w') as f:
        json.dump(results, f, indent=2) # 将结果写入 JSON 文件，保持格式化

    # 设置 GitHub Actions 输出变量。
    # `results_json_path` 将输出文件路径，`results_json_string` 将输出 JSON 内容的字符串表示。
    # 注意：`results_json_string` 有大小限制，对于大量数据不建议直接输出。
    print(f"::set-output name=results_json_path::{output_json_path}")
    print(f"::set-output name=results_json_string::{json.dumps(results)}")

if __name__ == "__main__":
    main()