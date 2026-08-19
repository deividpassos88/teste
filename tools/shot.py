"""Captura screenshot de uma URL via Chrome DevTools Protocol.

Uso: python3 tools/shot.py <url> <saida.png> [largura] [altura]
"""
import base64
import json
import sys
import time
import urllib.request
from urllib.error import URLError

from websocket import create_connection


def cdp_targets(port=9222):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json") as response:
        return json.load(response)


def new_tab(port=9222):
    url = f"http://127.0.0.1:{port}/json/new?about:blank"
    request = urllib.request.Request(url, method="PUT")
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except URLError:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/new?about:blank") as response:
            return json.load(response)


def close_tab(target_id, port=9222):
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/close/{target_id}"
        ).read()
    except Exception:
        pass


def capture(url, output, width=1600, height=1000, wait=3.0, full_page=True):
    tab = new_tab()
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    counter = {"id": 0}

    def send(method, params=None):
        counter["id"] += 1
        message_id = counter["id"]
        ws.send(json.dumps({
            "id": message_id,
            "method": method,
            "params": params or {},
        }))
        while True:
            data = json.loads(ws.recv())
            if data.get("id") == message_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})

    try:
        send("Page.enable")
        send("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 2,
            "mobile": False,
        })
        send("Page.navigate", {"url": url})
        time.sleep(wait)

        params = {"format": "png"}
        if full_page:
            metrics = send("Page.getLayoutMetrics")
            content = metrics.get("cssContentSize") or metrics["contentSize"]
            full_height = min(int(content["height"]), 12000)
            send("Emulation.setDeviceMetricsOverride", {
                "width": width,
                "height": full_height,
                "deviceScaleFactor": 2,
                "mobile": False,
            })
            time.sleep(0.6)

        result = send("Page.captureScreenshot", params)
        with open(output, "wb") as handle:
            handle.write(base64.b64decode(result["data"]))
        print(f"salvo: {output}")
    finally:
        ws.close()
        close_tab(tab["id"])


if __name__ == "__main__":
    target_url = sys.argv[1]
    destination = sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1600
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
    # Quarto argumento "fold" captura apenas a viewport (dobra inicial).
    fold = len(sys.argv) > 5 and sys.argv[5] == "fold"
    capture(target_url, destination, w, h, full_page=not fold)
