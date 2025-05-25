import requests
import json
from datetime import datetime
import sys
import argparse

# 移除 get_docker_hub_auth_token 函数

def fetch_paginated_data(url, headers=None):
    """
    通用函数，用于从支持分页的 API 获取所有数据。
    """
    all_results = []
    next_page = url
    while next_page:
        try:
            response = requests.get(next_page, headers=headers)
            response.raise_for_status()
            data = response.json()
            all_results.extend(data.get("results", []))
            next_page = data.get("next")
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from {next_page}: {e}")
            print(f"Response status: {response.status_code if 'response' in locals() else 'N/A'}")
            print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
            break
    return all_results

def main():
    parser = argparse.ArgumentParser(description="List Docker Hub images for a given namespace.")
    parser.add_argument('--namespace', type=str, required=True,
                        help='Docker Hub username or organization name (Namespace).')
    
    args = parser.parse_args()

    namespace = args.namespace

    if not namespace:
        print("错误: 未提供 --namespace 参数，无法查询 Docker Hub 镜像。", file=sys.stderr)
        sys.exit(1)

    # 移除认证相关的逻辑，因为 docker/login-action 已经处理了认证
    # 理论上，requests 不会自动使用 docker/login-action 的会话，
    # 但对于公共 API 访问，这通常不是问题。对于私有仓库，如果 Python 脚本直接访问 API 而不是通过 Docker CLI，
    # 你可能需要手动传递认证头（这通常通过获取 JWT Token 实现，但这里我们简化处理，
    # 依赖 docker/login-action 使得后续的 `docker` 命令可以直接使用认证）
    # 对于 requests 库直接访问 Docker Hub Registry API，匿名访问仍然有限制，
    # 并且对于私有仓库或避免速率限制，你需要一个 JWT Token。
    # 这里的假设是：如果你需要认证，你将通过 docker/login-action 登录，
    # 然后你的 Python 脚本主要用于查询公共可访问的元数据，或者你会通过其他方式处理私有 API 认证。
    headers = {} # 保持空的 headers，依赖 docker/login-action 的副作用或公共访问

    print(f"查询 Docker Hub 镜像，命名空间: {namespace}")
    print("-" * 50)

    # --- 获取仓库 (镜像) 列表 ---
    repos_url = f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/?page_size=100"
    repositories = fetch_paginated_data(repos_url, headers=headers)

    if not repositories:
        print(f"命名空间 '{namespace}' 下未找到任何仓库。")
        print(f"::set-output name=results_json_path::dockerhub_results.json")
        print(f"::set-output name=results_json_string::{json.dumps([])}")
        with open("dockerhub_results.json", 'w') as f:
            json.dump([], f, indent=2)
        return

    print(f"找到 {len(repositories)} 个仓库。")
    print("-" * 50)

    table_data = []
    json_output_data = [] 

    # --- 处理每个镜像及其标签 ---
    for repo in repositories:
        image_name = repo.get("name")
        if not image_name:
            continue

        tags_url = f"https://hub.docker.com/v2/repositories/{namespace}/{image_name}/tags?page_size=100"
        tags = fetch_paginated_data(tags_url, headers=headers)

        if not tags:
            table_data.append({
                "Image:Tag": f"{namespace}/{image_name}: (No Tags)",
                "ID (digest)": "N/A", "Pushed At": "N/A",
                "Size": "N/A", "Architectures": "N/A"
            })
            json_output_data.append({
                "image_name": f"{namespace}/{image_name}",
                "tag": "(No Tags)", "digest": "N/A",
                "pushed_at": "N/A", "size_bytes": "N/A",
                "size_mb": "N/A", "architectures": []
            })
            continue

        for tag_info in tags:
            tag_name = tag_info.get("name")
            last_updated = tag_info.get("last_updated")
            
            formatted_pushed_at = "N/A"
            if last_updated:
                try:
                    dt_object = datetime.strptime(last_updated, "%Y-%m-%dT%H:%M:%S.%fZ")
                    formatted_pushed_at = dt_object.strftime("%Y-%m-%d %H:%M:%S UTC")
                except ValueError:
                    formatted_pushed_at = last_updated

            full_size_bytes = tag_info.get("full_size", 0)
            full_size_mb = f"{(full_size_bytes / (1024 * 1024)):.2f} MB" if full_size_bytes else "0.00 MB"

            digest = "N/A"
            architectures = [] 
            architectures_for_json = [] 

            if tag_info.get("images"):
                for img in tag_info["images"]:
                    if img.get("digest"):
                        digest = img["digest"]
                    arch = img.get("architecture")
                    os_name = img.get("os")
                    
                    if arch and os_name and arch != 'unknown' and os_name != 'unknown':
                        arch_os_pair = f"{arch}/{os_name}"
                        architectures.append(arch_os_pair)
                        architectures_for_json.append(arch_os_pair)
            
            arch_str = ", ".join(sorted(list(set(architectures)))) if architectures else "N/A"

            table_data.append({
                "Image:Tag": f"{namespace}/{image_name}:{tag_name}",
                "ID (digest)": digest,
                "Pushed At": formatted_pushed_at,
                "Size": full_size_mb,
                "Architectures": arch_str
            })

            json_output_data.append({
                "image_name": f"{namespace}/{image_name}",
                "tag": tag_name,
                "digest": digest,
                "pushed_at": last_updated, 
                "size_bytes": full_size_bytes,
                "size_mb": float(full_size_mb.replace(' MB', '')) if full_size_mb != "N/A" else "N/A",
                "architectures": sorted(list(set(architectures_for_json))) 
            })

    if table_data:
        headers = ["Image:Tag", "ID (digest)", "Pushed At", "Size", "Architectures"]
        column_widths = {header: len(header) for header in headers}
        for row in table_data:
            for header in headers:
                column_widths[header] = max(column_widths[header], len(str(row.get(header, ""))))

        header_line = " | ".join(header.ljust(column_widths[header]) for header in headers)
        print(header_line)
        print("-+-".join("-" * column_widths[header] for header in headers))
        for row in table_data:
            row_line = " | ".join(str(row.get(header, "")).ljust(column_widths[header]) for header in headers)
            print(row_line)
    else:
        print("未找到任何镜像标签。")

    output_json_path = "dockerhub_results.json"
    with open(output_json_path, 'w') as f:
        json.dump(json_output_data, f, indent=2)
    
    print(f"::set-output name=results_json_path::{output_json_path}")
    print(f"::set-output name=results_json_string::{json.dumps(json_output_data)}")

if __name__ == "__main__":
    main()