import requests
import json
import argparse
import sys
from datetime import datetime
from urllib.parse import quote

def fetch_packages(namespace, is_org, headers):
    url = f"https://api.github.com/{'orgs' if is_org else 'users'}/{namespace}/packages?package_type=container"
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

def fetch_versions(namespace, pkg_name, is_org, headers):
    encoded_name = quote(pkg_name, safe='')
    url = f"https://api.github.com/{'orgs' if is_org else 'users'}/{namespace}/packages/container/{encoded_name}/versions"
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

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
        packages = fetch_packages(args.namespace, args.org, headers)
    except requests.HTTPError as e:
        print(f"❌ 获取包列表失败: {e}")
        sys.exit(1)

    if not packages:
        print("⚠️ 未找到任何容器镜像。")
        print("::set-output name=results_json_path::ghcr_results.json")
        print("::set-output name=results_json_string::[]")
        with open("ghcr_results.json", "w") as f:
            json.dump([], f, indent=2)
        return

    results = []
    for pkg in packages:
        name = pkg.get("name")
        print(f"📦 镜像: ghcr.io/{args.namespace}/{name}")
        try:
            versions = fetch_versions(args.namespace, name, args.org, headers)
        except requests.HTTPError as e:
            print(f"  ❌ 获取版本失败: {e}")
            continue

        if not versions:
            print("  ⚠️ 没有标签版本。")
            continue

        for version in versions:
            tag_names = version.get("metadata", {}).get("container", {}).get("tags", [])
            pushed_at = version.get("created_at")
            digest = version.get("name")
            size_bytes = version.get("metadata", {}).get("container", {}).get("size", 0)
            formatted_time = datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S UTC") if pushed_at else "N/A"
            size_mb = round(size_bytes / (1024 * 1024), 2)

            for tag in tag_names:
                results.append({
                    "image": f"ghcr.io/{args.namespace}/{name}",
                    "tag": tag,
                    "digest": digest,
                    "pushed_at": pushed_at,
                    "size_bytes": size_bytes,
                    "size_mb": size_mb
                })

    if results:
        print(f"\n✅ 共记录 {len(results)} 个标签版本")
    else:
        print("\n⚠️ 未找到任何标签版本。")

    output_path = "ghcr_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"::set-output name=results_json_path::{output_path}")
    print(f"::set-output name=results_json_string::{json.dumps(results)}")

if __name__ == "__main__":
    main()
