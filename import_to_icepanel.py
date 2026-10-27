#!/usr/bin/env python3
"""将 icepanel-landscape.json 导入 IcePanel（Model-as-code API）。

用法：
  python3 import_to_icepanel.py <landscape_id>   # 导入到 versions/latest
  python3 import_to_icepanel.py --list-orgs      # 列出可访问的组织与 landscape

环境变量（或本目录下的 .env 文件）：
  ICEPANEL_API_KEY      - API 密钥，见 https://icepanel.dev/integrations/api-sdk
  ICEPANEL_LANDSCAPE_ID - 可选，未传命令行参数时使用
"""
import json
import os
import sys
import urllib.request
import urllib.error

BASE = "https://api.icepanel.io/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD_FILE = os.path.join(HERE, "icepanel-landscape.json")


def load_env():
    env_file = os.path.join(HERE, ".env")
    if os.path.isfile(env_file):
        for line in open(env_file):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    key = os.environ.get("ICEPANEL_API_KEY", "").strip()
    if not key:
        sys.exit("缺少 ICEPANEL_API_KEY，请先写入 .env 或导出该环境变量。")
    return key


def request(method, path, api_key, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers={"X-API-Key": api_key,
                 "Accept": "application/json"},
    )
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        sys.exit(f"API 错误 {e.code} {e.reason}：\n{detail}")


def list_orgs_and_landscapes(api_key):
    status, data = request("GET", "/organizations", api_key)
    orgs = data if isinstance(data, list) else data.get("organizations", [])
    for org in orgs:
        print(f"组织：{org.get('name')}  ({org.get('id')})")
        status, lands = request(
            "GET", f"/organizations/{org['id']}/landscapes", api_key)
        for land in (lands if isinstance(lands, list) else lands.get("landscapes", [])):
            print(f"   Landscape：{land.get('name')}  ({land.get('id')})")
    sys.exit(0)


def main():
    api_key = load_env()
    argv = sys.argv[1:]

    if "--list-orgs" in argv or "--list" in argv:
        list_orgs_and_landscapes(api_key)

    landscape_id = argv[0] if argv else os.environ.get("ICEPANEL_LANDSCAPE_ID")
    if not landscape_id:
        sys.exit("用法：python3 import_to_icepanel.py <landscape_id>\n"
                 "  （或运行 --list-orgs 查找 ID）")

    with open(PAYLOAD_FILE) as f:
        payload = json.load(f)

    print(f"正在导入 {len(payload['modelObjects'])} 个对象、"
          f"{len(payload['modelConnections'])} 条连接 ...")
    status, result = request(
        "POST", f"/landscapes/{landscape_id}/versions/latest/import",
        api_key, payload)
    print(f"导入成功（HTTP {status}）—— 打开 IcePanel 中的 landscape 即可查看。")
    print(json.dumps(result, indent=2)[:2000])


if __name__ == "__main__":
    main()
