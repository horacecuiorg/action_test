import requests
import json
import argparse
import sys
from datetime import datetime
from urllib.parse import quote

def fetch_paginated_data(url, headers):
    all_results = []
    next_page = url
    while next_page:
        try:
            r = requests.get(next_page, headers=headers)
            r.raise_for_status()
            data = r.json()
            all_results.extend(data.get("packages", []) or data.get("results", []) or data)
            # 处理分页
            if 'Link' in r.headers:
                links = r.headers['Link'].split(",")
                next_url = None
                for link in links:
                    if 'rel="next"' in link:
                        next_url = link[link.find("<")+1:link.find(">")]
                        break
                next_page = next_url
            else:
                next_page = None
        except requests.RequestException as e:
            print(f"❌ 请求失败: {e}", file=sys.stderr)
            break
    return all_results

def fetch_versions(namespace, pkg_name, is_org, headers):
    encoded_name = quote(pkg_name, safe='')
    url = f"https://api.github.com/{'orgs' if is_org else 'users'}/{namespace}/packages/container/{encoded_name}/versions"
    return fetch_paginated_data(url, headers)

def main():
    parser = argparse.ArgumentParser(description="List GHCR container packages for a namespace.")
    parser.add_argument("--namespace", type=str, required=True, help="GitHub username or organization name")
    parser.add_argument("--org", action="store_true", help="Specify if the namespace is an organization")
    parser.add_argument("--token", type=str, required=True, help="GitHub token with read:packages scope")
    args = parser.parse_args()

    headers = {
        "Authorization": f"Bearer {args.token}",
        "Accept": "application/vnd.github+json"
    }

    if not args.namespace:
        print("错误: --namespace 不能为空", file=sys.stderr)
        sys.exit(1)

    print(f"查询 GHCR 镜像（命名空间: {args.namespace}, 类型: {'组织' if args.org else '用户'}）")
    print("-" * 50)

    try:
        packages = fetch_paginated_data(
            f"https://api.github.com/{'orgs' if args.org else 'users'}/{args.namespace}/packages?package_type=container",
            headers)
    except requests.HTTPError as e:
        print(f"❌ 获取包列表失败: {e}", file=sys.stderr)
        sys.exit(1)

    if not packages:
        print("⚠️ 未找到任何容器镜像。")
        print("::set-output name=results_json_path::ghcr_results.json")
        print("::set-output name=results_json_string::[]")
        with open("ghcr_results.json", "w") as f:
            json.dump([], f, indent=2)
        return

    results = []
    table_data = []

    for pkg in packages:
        name = pkg.get("name")
        print(f"📦 镜像: ghcr.io/{args.namespace}/{name}")
        try:
            versions = fetch_versions(args.namespace, name, args.org, headers)
        except requests.HTTPError as e:
            print(f"  ❌ 获取版本失败: {e}", file=sys.stderr)
            continue

        if not versions:
            print("  ⚠️ 没有标签版本。")
            # 对应无版本的条目，保持输出一致
            table_data.append({
                "Image:Tag": f"ghcr.io/{args.namespace}/{name}:(No Tags)",
                "ID (digest)": "N/A",
                "Pushed At": "N/A",
                "Size": "N/A",
                "Architectures": "N/A"
            })
            results.append({
                "image_name": f"ghcr.io/{args.namespace}/{name}",
                "tag": "(No Tags)",
                "digest": "N/A",
                "pushed_at": "N/A",
                "size_bytes": 0,
                "size_mb": 0.0,
                "architectures": []
            })
            continue

        for version in versions:
            tag_names = version.get("metadata", {}).get("container", {}).get("tags", [])
            if not tag_names:
                tag_names = ["latest"]

            pushed_at = version.get("updated_at") or version.get("created_at") or "N/A"
            digest = version.get("name") or "N/A"
            size_bytes = version.get("metadata", {}).get("container", {}).get("size", 0)
            size_mb = float(size_bytes) / (1024 * 1024) if size_bytes else 0.0

            formatted_pushed_at = "N/A"
            if pushed_at != "N/A":
                try:
                    dt_object = datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
                    formatted_pushed_at = dt_object.strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    formatted_pushed_at = pushed_at

            arch_str = "N/A"
            architectures = []  # 这里保持空列表，跟dockerhub脚本一致

            for tag in tag_names:
                image_ref = f"ghcr.io/{args.namespace}/{name}"
                table_data.append({
                    "Image:Tag": f"{image_ref}:{tag}",
                    "ID (digest)": digest,
                    "Pushed At": formatted_pushed_at,
                    "Size": f"{size_mb:.2f} MB" if size_bytes else "0.00 MB",
                    "Architectures": arch_str
                })
                results.append({
                    "image_name": image_ref,
                    "tag": tag,
                    "digest": digest,
                    "pushed_at": pushed_at,
                    "size_bytes": size_bytes,
                    "size_mb": size_mb,
                    "architectures": architectures
                })

    # 打印表格
    if table_data:
        headers = ["Image:Tag", "ID (digest)", "Pushed At", "Size", "Architectures"]
        column_widths = {h: len(h) for h in headers}
        for row in table_data:
            for h in headers:
                column_widths[h] = max(column_widths[h], len(str(row.get(h, ""))))
        print(" | ".join(h.ljust(column_widths[h]) for h in headers))
        print("-+-".join("-" * column_widths[h] for h in headers))
        for row in table_data:
            print(" | ".join(str(row.get(h, "")).ljust(column_widths[h]) for h in headers))
    else:
        print("未找到任何标签版本。")

    output_path = "ghcr_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"::set-output name=results_json_path::{output_path}")
    print(f"::set-output name=results_json_string::{json.dumps(results)}")

if __name__ == "__main__":
    main()
