"""Captura a aba 'Entregas vs Pedido' clicando no menu lateral."""
import base64
import json
import sys
import time
import urllib.request

from websocket import create_connection


def main(output, width=1440, height=900, month="2026-07"):
    request = urllib.request.Request(
        "http://127.0.0.1:9222/json/new?about:blank", method="PUT"
    )
    tab = json.load(urllib.request.urlopen(request))
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    counter = {"id": 0}

    def send(method, params=None):
        counter["id"] += 1
        message_id = counter["id"]
        ws.send(json.dumps({
            "id": message_id, "method": method, "params": params or {},
        }))
        while True:
            data = json.loads(ws.recv())
            if data.get("id") == message_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})

    def evaluate(expression):
        return send("Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        })

    try:
        send("Page.enable")
        send("Runtime.enable")
        send("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height,
            "deviceScaleFactor": 2, "mobile": False,
        })
        send("Page.navigate", {"url": "http://127.0.0.1:8765/"})
        time.sleep(3.5)
        evaluate("document.querySelector('#delivery-nav').click()")
        time.sleep(1.2)
        # Escolhe um mes com faturamento real para a tela nao ficar vazia.
        evaluate(
            "(() => { const f = document.querySelector('#delivery-month');"
            f" f.value = '{month}';"
            " f.dispatchEvent(new Event('change', {bubbles: true})); })()"
        )
        time.sleep(3.0)
        result = send("Page.captureScreenshot", {"format": "png"})
        with open(output, "wb") as handle:
            handle.write(base64.b64decode(result["data"]))
        print(f"salvo: {output}")
    finally:
        ws.close()
        urllib.request.urlopen(
            f"http://127.0.0.1:9222/json/close/{tab['id']}"
        ).read()


if __name__ == "__main__":
    main(sys.argv[1], month=sys.argv[2] if len(sys.argv) > 2 else "2026-07")
