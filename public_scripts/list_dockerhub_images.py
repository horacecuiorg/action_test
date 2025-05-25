import requests
import json
from datetime import datetime
import sys
import argparse

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
            all_results.extend(data.get("packages", []) or data.get("results", []))
            next_page = None
            # GitHub REST API分页通过 Link header给出，这里简单处理翻页
            if 'Link' in response.headers:
                links = response.headers['Link'].split(",")
                next_url = None
                for link in links:
                    if 'rel="next"' in link:
                        next_url = link[link.find("<")+1:link.find(">")]
                        break
                next_page = next_url
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from {next_page}: {e}")
            print(f"Response status: {response.status_code if 'response' in locals() else 'N/A'}")
            print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
            break
    return all_results

def get_manifest_and_size(repo_name, tag, token):
    """
    通过 Docker Registry API v2 获取指定镜像标签的 manifest，计算总大小。
    """
    url = f"https://ghcr.io/v2/{repo_name}/manifests/{tag}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json"
    }
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        manifest = resp.json()
        layers = manifest.get("layers", [])
        size_bytes = sum(layer.get("size", 0) for layer in layers)
        digest = manifest.get("config", {}).get("digest", "N/A")
        return digest, size_bytes
    except requests.exceptions.RequestException as e:
        print(f"  ❌ 获取 manifest 失败: {e}")
        return "N/A", 0

def main():
    parser = argparse.ArgumentParser(description="List GHCR container images for a given org namespace.")
    parser.add_argument('--namespace', type=str, required=True,
                        help='GitHub organization name (namespace).')
    parser.add_argument('--token', type=str, required=True,
                        help='GitHub personal access token with read:packages scope.')
    
    args = parser.parse_args()

    namespace = args.namespace
    token = args.token

    if not namespace or not token:
        print("错误: 必须提供 --namespace 和 --token 参数。", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    print(f"查询 GHCR 镜像（命名空间: {namespace}，类型: 组织）")
    print("-" * 50)

    # --- 获取容器包列表 ---
    packages_url = f"https://api.github.com/orgs/{namespace}/packages?package_type=container"
    packages = fetch_paginated_data(packages_url, headers=headers)

    if not packages:
        print(f"命名空间 '{namespace}' 下未找到任何容器包。")
        print(f"::set-output name=results_json_path::ghcr_results.json")
        print(f"::set-output name=results_json_string::{json.dumps([])}")
        with open("ghcr_results.json", 'w') as f:
            json.dump([], f, indent=2)
        return

    print(f"找到 {len(packages)} 个容器包。")
    print("-" * 50)

    table_data = []
    json_output_data = []

    # --- 处理每个包及其标签（版本） ---
    for pkg in packages:
        package_name = pkg.get("name")
        full_package_name = f"{namespace}/{package_name}"

        tags_url = f"https://api.github.com/orgs/{namespace}/packages/container/{package_name}/versions"
        try:
            resp = requests.get(tags_url, headers=headers)
            resp.raise_for_status()
            versions = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"📦 镜像: ghcr.io/{namespace}/{package_name}")
            print(f"  ❌ 获取版本失败: {e}")
            continue

        if not versions:
            table_data.append({
                "Image:Tag": f"ghcr.io/{namespace}/{package_name}: (No Tags)",
                "ID (digest)": "N/A", "Pushed At": "N/A",
                "Size": "N/A", "Architectures": "N/A"
            })
            json_output_data.append({
                "image_name": f"ghcr.io/{namespace}/{package_name}",
                "tag": "(No Tags)", "digest": "N/A",
                "pushed_at": "N/A", "size_bytes": 0,
                "size_mb": 0.0, "architectures": []
            })
            continue

        for version in versions:
            tag_name = version.get("metadata", {}).get("container", {}).get("tags", [])
            tag_name = tag_name[0] if tag_name else "latest"
            pushed_at = version.get("updated_at") or version.get("created_at") or "N/A"

            # 获取 manifest 及大小
            digest, size_bytes = get_manifest_and_size(package_name, tag_name, token)

            formatted_pushed_at = "N/A"
            if pushed_at != "N/A":
                try:
                    dt_object = datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
                    formatted_pushed_at = dt_object.strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    formatted_pushed_at = pushed_at

            size_mb = float(size_bytes) / (1024 * 1024) if size_bytes else 0.0
            size_mb_str = f"{size_mb:.2f} MB" if size_bytes else "0.00 MB"

            # 架构信息 GHCR API不直接返回，需要从manifest或者metadata里解析（这里示例简化为 N/A）
            arch_str = "N/A"
            architectures = []

            image_ref = f"ghcr.io/{namespace}/{package_name}"

            table_data.append({
                "Image:Tag": f"{image_ref}:{tag_name}",
                "ID (digest)": digest,
                "Pushed At": formatted_pushed_at,
                "Size": size_mb_str,
                "Architectures": arch_str
            })

            json_output_data.append({
                "image_name": image_ref,
                "tag": tag_name,
                "digest": digest,
                "pushed_at": pushed_at,
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "architectures": architectures
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

    output_json_path = "ghcr_results.json"
    with open(output_json_path, 'w') as f:
        json.dump(json_output_data, f, indent=2)

    print(f"::set-output name=results_json_path::{output_json_path}")
    print(f"::set-output name=results_json_string::{json.dumps(json_output_data)}")

if __name__ == "__main__":
    main()
