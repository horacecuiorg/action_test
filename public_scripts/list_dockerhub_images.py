import requests
import os
import json
from datetime import datetime

def get_docker_hub_auth_token(username, password):
    """尝试获取 Docker Hub 认证 token。"""
    auth_url = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/ubuntu:pull"
    try:
        response = requests.get(auth_url, auth=(username, password))
        response.raise_for_status()
        return response.json().get("token")
    except requests.exceptions.RequestException as e:
        print(f"Error getting Docker Hub auth token: {e}")
        return None

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
            break
    return all_results

def main():
    namespace = os.environ.get("TARGET_NAMESPACE")
    use_auth_str = os.environ.get("USE_DOCKER_HUB_AUTH", "false").lower()
    use_auth = use_auth_str == "true"

    username = os.environ.get("DOCKER_HUB_USERNAME")
    password = os.environ.get("DOCKER_HUB_PASSWORD")

    headers = {}
    if use_auth:
        if not username or not password:
            print("Warning: USE_DOCKER_HUB_AUTH is true, but DOCKER_HUB_USERNAME or DOCKER_HUB_PASSWORD is not set.")
            print("Proceeding without authentication. This may lead to rate limits or failure for private repos.")
        else:
            auth_token = get_docker_hub_auth_token(username, password)
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
                print("Authenticated successfully to Docker Hub.")
            else:
                print("Failed to authenticate to Docker Hub. Proceeding without authentication.")


    print(f"Listing Docker Hub images for namespace: {namespace}")
    print(f"Authentication used: {use_auth}")
    print("-" * 50)

    # --- Fetch Repositories (Images) ---
    repos_url = f"https://hub.docker.com/v2/namespaces/{namespace}/repositories?page_size=100"
    repositories = fetch_paginated_data(repos_url, headers=headers)

    if not repositories:
        print(f"No repositories found for namespace {namespace}.")
        # 也确保 JSON 输出是空的或表示无数据
        with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
            print(f'docker_hub_results_json=[]', file=fh)
        return

    print(f"Found {len(repositories)} repositories.")
    print("-" * 50)

    # Prepare data for table and JSON output
    table_data = []
    json_output_data = [] # New list to store data for JSON

    # --- Process Each Image and its Tags ---
    for repo in repositories:
        image_name = repo.get("name")
        if not image_name:
            continue

        tags_url = f"https://hub.docker.com/v2/repositories/{namespace}/{image_name}/tags?page_size=100"
        tags = fetch_paginated_data(tags_url, headers=headers)

        if not tags:
            # Add entry for images with no tags for both table and JSON
            table_data.append({
                "Image:Tag": f"{namespace}/{image_name}: (No Tags)",
                "ID (digest)": "N/A",
                "Pushed At": "N/A",
                "Size": "N/A",
                "Architectures": "N/A"
            })
            json_output_data.append({
                "image_name": f"{namespace}/{image_name}",
                "tag": "(No Tags)",
                "digest": "N/A",
                "pushed_at": "N/A",
                "size_mb": "N/A",
                "architectures": []
            })
            continue

        for tag_info in tags:
            tag_name = tag_info.get("name")
            last_updated = tag_info.get("last_updated")
            
            # Format Pushed At for better readability
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
            architectures = [] # For internal list of arch/os strings
            architectures_for_json = [] # For JSON output as a list of strings
            
            if tag_info.get("images"):
                for img in tag_info["images"]:
                    if img.get("digest"):
                        digest = img["digest"]
                    arch = img.get("architecture")
                    os_name = img.get("os")
                    
                    if arch and os_name and arch != 'unknown' and os_name != 'unknown':
                        arch_os_pair = f"{arch}/{os_name}"
                        architectures.append(arch_os_pair)
                        architectures_for_json.append(arch_os_pair) # Add to JSON specific list
            
            # Ensure uniqueness and sort for display
            arch_str = ", ".join(sorted(list(set(architectures)))) if architectures else "N/A"

            # Add to table data
            table_data.append({
                "Image:Tag": f"{namespace}/{image_name}:{tag_name}",
                "ID (digest)": digest,
                "Pushed At": formatted_pushed_at,
                "Size": full_size_mb,
                "Architectures": arch_str
            })

            # Add to JSON output data
            json_output_data.append({
                "image_name": f"{namespace}/{image_name}",
                "tag": tag_name,
                "digest": digest,
                "pushed_at": last_updated, # Use original ISO format for JSON
                "size_bytes": full_size_bytes,
                "size_mb": float(full_size_mb.replace(' MB', '')) if full_size_mb != "N/A" else "N/A",
                "architectures": sorted(list(set(architectures_for_json))) # Ensure unique and sorted for JSON
            })

    # Print data in a table format (for console output)
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
        print("No image tags found for the specified namespace.")

    # --- Write JSON output to GITHUB_OUTPUT ---
    # GITHUB_OUTPUT 是一个特殊的环境变量，GitHub Actions 会从这里读取输出
    # 将 JSON 字符串写入临时文件，然后将其路径作为输出，或者直接写入
    # 对于大的JSON，最好写入文件然后将文件路径作为输出，或者用base64编码
    # 但GitHub Actions的输出变量有大小限制，直接写入文件更可靠
    output_json_path = "docker_hub_results.json"
    with open(output_json_path, 'w') as f:
        json.dump(json_output_data, f, indent=2)
    
    print(f"::set-output name=docker_hub_results_path::{output_json_path}")
    print(f"::set-output name=docker_hub_results_json_string::{json.dumps(json_output_data)}") # 仅用于小量数据，有大小限制

if __name__ == "__main__":
    main()
