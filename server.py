import argparse
import ctypes
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from ctypes import wintypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree as ET


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = APP_DIR / "data"
DATABASE_PATH = DATA_DIR / "nfe_index.db"
DEFAULT_SHARE = r"\\192.168.2.6\erp\SP\nfe"
SALE_CFOPS = {"5101", "6101", "7101"}
ULIANA_COMPONENTES_CFOPS = {"6102", "6103"}
HONDA_INDUSTRIALIZATION_CFOP = "5124"
INDEX_RULES_VERSION = "20260801-uliana-componentes"
AUTO_REFRESH_SECONDS = 5 * 60
# Senha administrativa: definida em NFE_ADMIN_PASSWORD. Sem a variavel de
# ambiente o sistema continua aceitando a senha historica, que fica gravada
# aqui apenas como hash PBKDF2 com salt (nunca em texto aberto).
ADMIN_PASSWORD = os.environ.get("NFE_ADMIN_PASSWORD", "").strip()
ADMIN_PASSWORD_FALLBACK_HASH = (
    "55eba93633726580735321340af5d8ee:"
    "3a7df2d78567b8130b7750ef97e91f80a2b091b560d173faa0aff571e8c8e506"
)
AUTH_TOKEN_TTL_SECONDS = 8 * 60 * 60
MAX_WORKERS = 8
MISSING_INVOICE_LIMIT = 100
SEQUENCE_FILENAME = re.compile(r"^01001(\d{7})\.xml$", re.IGNORECASE)
SEQUENCE_EXCLUSION_FILENAME = re.compile(
    r"^01001(\d{7})_(?:Cancel|Inut)\.xml$", re.IGNORECASE
)

STATE_LOCK = threading.Lock()
SCAN_LOCK = threading.Lock()
AUTH_LOCK = threading.Lock()
RECOVERY_LOCK = threading.Lock()
AUTH_TOKENS = {}
STATE = {
    "running": False,
    "phase": "idle",
    "message": "Aguardando primeira leitura",
    "files_total": 0,
    "files_pending": 0,
    "files_processed": 0,
    "items_found": 0,
    "errors": 0,
    "last_scan": None,
    "started_at": None,
    "missing_invoices": [],
    "missing_total": 0,
    "datasul_available": False,
    "recovery_running": False,
    "recovery_message": "Sequência ainda não verificada",
}


# Ordem das colunas gravadas em `items` por persist_result.
# Precisa conter exatamente as chaves montadas em parse_nfe, exceto
# `source_file` (que nao existe na tabela) e `file_path` (passado a parte).
ITEM_COLUMNS = (
    "n_item",
    "access_key",
    "invoice_number",
    "billing_number",
    "issued_at",
    "issue_date",
    "issue_display",
    "product_code",
    "ean",
    "description",
    "client_code",
    "ncm",
    "benefit_code",
    "cfop",
    "commercial_unit",
    "quantity_raw",
    "quantity",
    "unit_value",
    "product_value",
    "tax_ean",
    "tax_unit",
    "tax_quantity",
    "tax_unit_value",
    "total_indicator",
    "order_number",
    "order_item",
    "manufacturer",
    "plant",
    "source_name",
)


def update_state(**changes):
    with STATE_LOCK:
        STATE.update(changes)


def local_network_ip():
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.connect(("192.168.2.6", 445))
        return connection.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "IP-DESTE-COMPUTADOR"
    finally:
        connection.close()


def state_snapshot():
    with STATE_LOCK:
        return dict(STATE)


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(parent, name, default=""):
    if parent is None:
        return default
    for child in parent:
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return default


def first_descendant(parent, name):
    if parent is None:
        return None
    for node in parent.iter():
        if local_name(node.tag) == name:
            return node
    return None


def decimal_number(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def format_issue_date(raw_value):
    if not raw_value:
        return "", ""
    try:
        parsed = datetime.fromisoformat(raw_value)
        return parsed.date().isoformat(), parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return raw_value[:10], raw_value


def classify_product(code):
    normalized = (code or "").strip().upper()

    # Regras mais especificas precisam vir antes das regras por prefixo.
    if normalized.startswith("UC"):
        if normalized.endswith("PA"):
            return "Uliana Componentes", "Reposicao"
        return "Uliana Componentes", "Uliana Componentes"

    if normalized in {"PS00100", "PS00110", "PS00200"}:
        return "Prima Soles", "Prima Soles"
    if normalized in {"VL00100", "VL00110"}:
        return "Valeo", "Valeo"
    if normalized == "MW13000":
        return "MWM", "MWM"
    if normalized == "IB00010":
        return "Reydel", "Reydel"
    if normalized in {"IA00100", "IA00100N", "IA00700", "IA00800"}:
        return "Inalfa", "Inalfa"

    if normalized.startswith("PG"):
        if normalized.endswith(("PA", "REV")):
            return "PSA", "Reposicao"
        return "PSA", "PSA"

    if normalized.startswith("HD"):
        if normalized.endswith(("PA", "REV")):
            return "Honda", "Reposicao"
        if normalized.endswith("ITP"):
            return "Honda", "Paulinia"
        return "Honda", "Revisar"

    if normalized.startswith("SC"):
        if normalized.endswith(("PA", "REV")):
            return "Scania", "Reposicao"
        if normalized.endswith("E"):
            return "Scania", "Exportacao"
        if re.fullmatch(r"SC\d+", normalized):
            return "Scania", "Scania"
        return "Scania", "Revisar"

    if normalized.startswith("GM"):
        if normalized.endswith("REV"):
            return "GM", "Reposicao"
        if normalized.endswith("SJC"):
            return "GM", "Sao Jose dos Campos"
        if normalized.endswith("MC"):
            return "GM", "Mogi"
        if re.fullmatch(r"GM\d+", normalized):
            return "GM", "Sao Caetano do Sul"
        return "GM", "Revisar"

    if normalized.startswith(("VK", "MN")):
        if normalized.endswith(("PA", "REV")):
            return "Volkswagen", "Reposicao PA"
        if normalized.startswith("MN") or normalized in {
            "VK16000", "VK18000", "VK20180", "VK20210", "VK20100",
        }:
            return "Volkswagen", "MAN"
        if normalized in {"VK24000", "VK24010"}:
            return "Volkswagen", "Sao Carlos"
        if normalized.endswith("CUR"):
            return "Volkswagen", "Curitiba"
        if normalized.endswith("T"):
            return "Volkswagen", "Taubate"
        if re.fullmatch(r"VK\d+", normalized):
            return "Volkswagen", "Anchieta"
        return "Volkswagen", "Revisar"

    return "Nao classificado", "Nao classificado"


def file_kind(path):
    name = os.path.basename(path).upper()
    if "_CANCEL" in name:
        return "cancelled"
    if "_CCE" in name:
        return "correction"
    return "nfe"


def process_xml_entry(path):
    kind = file_kind(path)
    if kind != "nfe":
        return {"status": kind, "items": [], "error": ""}
    return parse_nfe(path)


def parse_nfe(path):
    try:
        root = ET.parse(path).getroot()
        inf_nfe = first_descendant(root, "infNFe")
        if inf_nfe is None:
            return {"status": "ignored", "items": [], "error": ""}

        ide = first_descendant(inf_nfe, "ide")
        cobr = first_descendant(inf_nfe, "cobr")
        fat = first_descendant(cobr, "fat")

        invoice_number = child_text(ide, "nNF")
        operation_nature = child_text(ide, "natOp")
        issued_at = child_text(ide, "dhEmi")
        billing_number = child_text(fat, "nFat")
        issue_date, issue_display = format_issue_date(issued_at)
        access_key = inf_nfe.attrib.get("Id", "").replace("NFe", "", 1)

        items = []
        for detail in inf_nfe.iter():
            if local_name(detail.tag) != "det":
                continue
            product = first_descendant(detail, "prod")
            if product is None:
                continue

            product_code = child_text(product, "cProd")
            cfop = child_text(product, "CFOP")
            is_regular_sale = cfop in SALE_CFOPS
            is_uliana_componentes_sale = (
                cfop in ULIANA_COMPONENTES_CFOPS
                and product_code.strip().upper().startswith("UC")
            )
            is_honda_industrialization = (
                cfop == HONDA_INDUSTRIALIZATION_CFOP
                and "INDUSTRIALIZA" in operation_nature.upper()
                and product_code.strip().upper().startswith("HD")
            )
            if not (
                is_regular_sale
                or is_uliana_componentes_sale
                or is_honda_industrialization
            ):
                continue

            manufacturer, plant = classify_product(product_code)
            quantity_raw = child_text(product, "qCom")

            items.append({
                "n_item": detail.attrib.get("nItem", ""),
                "access_key": access_key,
                "invoice_number": invoice_number,
                "billing_number": billing_number,
                "issued_at": issued_at,
                "issue_date": issue_date,
                "issue_display": issue_display,
                "product_code": product_code,
                "ean": child_text(product, "cEAN"),
                "description": child_text(product, "xProd"),
                "client_code": child_text(detail, "infAdProd"),
                "ncm": child_text(product, "NCM"),
                "benefit_code": child_text(product, "cBenef"),
                "cfop": cfop,
                "commercial_unit": child_text(product, "uCom"),
                "quantity_raw": quantity_raw,
                "quantity": decimal_number(quantity_raw),
                "unit_value": child_text(product, "vUnCom"),
                "product_value": child_text(product, "vProd"),
                "tax_ean": child_text(product, "cEANTrib"),
                "tax_unit": child_text(product, "uTrib"),
                "tax_quantity": child_text(product, "qTrib"),
                "tax_unit_value": child_text(product, "vUnTrib"),
                "total_indicator": child_text(product, "indTot"),
                "order_number": child_text(product, "xPed"),
                "order_item": child_text(product, "nItemPed"),
                "manufacturer": manufacturer,
                "plant": plant,
                "source_file": str(path),
                "source_name": os.path.basename(path),
            })

        return {
            "status": "accepted" if items else "ignored",
            "items": items,
            "error": "",
        }
    except (ET.ParseError, OSError, ValueError) as error:
        return {"status": "error", "items": [], "error": str(error)[:500]}


def new_database_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


@contextmanager
def connect_database():
    """Abre a conexao e SEMPRE fecha ao sair do bloco.

    O `with` nativo do sqlite3 controla apenas a transacao (commit no
    sucesso, rollback no erro) e nunca fecha o descritor. Sem o close
    explicito cada requisicao vazava file descriptors ate o servidor
    esbarrar no limite do sistema operacional.
    """
    connection = new_database_connection()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with connect_database() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                n_item TEXT,
                access_key TEXT,
                invoice_number TEXT,
                billing_number TEXT,
                issued_at TEXT,
                issue_date TEXT,
                issue_display TEXT,
                product_code TEXT,
                ean TEXT,
                description TEXT,
                client_code TEXT,
                ncm TEXT,
                benefit_code TEXT,
                cfop TEXT,
                commercial_unit TEXT,
                quantity_raw TEXT,
                quantity REAL,
                unit_value TEXT,
                product_value TEXT,
                tax_ean TEXT,
                tax_unit TEXT,
                tax_quantity TEXT,
                tax_unit_value TEXT,
                total_indicator TEXT,
                order_number TEXT,
                order_item TEXT,
                manufacturer TEXT,
                plant TEXT,
                source_name TEXT,
                UNIQUE(file_path, n_item)
            );

            CREATE INDEX IF NOT EXISTS idx_items_manufacturer
                ON items(manufacturer, plant);
            CREATE INDEX IF NOT EXISTS idx_items_issue_date
                ON items(issue_date);
            CREATE INDEX IF NOT EXISTS idx_items_product_code
                ON items(product_code);
            CREATE INDEX IF NOT EXISTS idx_items_invoice
                ON items(invoice_number);
            CREATE INDEX IF NOT EXISTS idx_items_access_key
                ON items(access_key, n_item, quantity);

            CREATE TABLE IF NOT EXISTS delivery_programs (
                month TEXT NOT NULL,
                manufacturer TEXT NOT NULL,
                plant TEXT NOT NULL,
                product_code TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (month, manufacturer, plant, product_code)
            );

            CREATE TABLE IF NOT EXISTS security_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recovery_attempts (
                invoice_number INTEGER PRIMARY KEY,
                attempted_at TEXT NOT NULL,
                result TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT ''
            );
        """)
        item_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(items)")
        }
        if "client_code" not in item_columns:
            connection.execute(
                "ALTER TABLE items ADD COLUMN client_code TEXT DEFAULT ''"
            )

        rules_row = connection.execute(
            "SELECT value FROM security_settings WHERE key = 'system:index_rules_version'"
        ).fetchone()
        if rules_row is None or rules_row["value"] != INDEX_RULES_VERSION:
            # Reprocessa uma unica vez os XMLs ja indexados quando as regras mudam.
            connection.execute("UPDATE files SET mtime_ns = -1")
            connection.execute(
                """
                INSERT INTO security_settings(key, value, updated_at)
                VALUES ('system:index_rules_version', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (INDEX_RULES_VERSION, datetime.now().isoformat(timespec="seconds")),
            )


def persist_result(connection, entry, result):
    path = entry.path
    connection.execute("DELETE FROM items WHERE file_path = ?", (path,))
    if result["items"]:
        # So e considerado duplicata quando access_key + n_item + quantity
        # forem todos iguais em outro arquivo. Se a quantidade for
        # diferente, as duas linhas sao mantidas (pode ser reemissao
        # legitima com quantidade distinta).
        keys = {
            (item["access_key"], item["n_item"], item["quantity"])
            for item in result["items"]
            if item["access_key"]
        }
        for access_key, n_item, quantity in keys:
            connection.execute(
                """
                DELETE FROM items
                WHERE access_key = ? AND n_item = ? AND quantity = ?
                  AND file_path != ?
                """,
                (access_key, n_item, quantity, path),
            )

        placeholders = ", ".join("?" for _ in ITEM_COLUMNS)
        columns = ", ".join(("file_path",) + ITEM_COLUMNS)
        sql = f"INSERT OR REPLACE INTO items ({columns}) VALUES (?, {placeholders})"
        rows = []
        for item in result["items"]:
            rows.append((path,) + tuple(item[column] for column in ITEM_COLUMNS))
        connection.executemany(sql, rows)

    stat = entry.stat(follow_symlinks=False)
    connection.execute("""
        INSERT INTO files(path, mtime_ns, size, status, error, processed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            mtime_ns = excluded.mtime_ns,
            size = excluded.size,
            status = excluded.status,
            error = excluded.error,
            processed_at = excluded.processed_at
    """, (
        path,
        stat.st_mtime_ns,
        stat.st_size,
        result["status"],
        result["error"],
        datetime.now().isoformat(timespec="seconds"),
    ))


def list_xml_entries(share_path):
    entries = []
    with os.scandir(share_path) as iterator:
        for entry in iterator:
            if not entry.is_file(follow_symlinks=False):
                continue
            name = entry.name.lower()
            if not name.endswith(".xml"):
                continue
            entries.append(entry)
    return entries


def sequence_numbers(entries):
    """Separa NF-e normal de cancelamentos e inutilizacoes da serie 1."""
    existing = set()
    excluded = set()
    for entry in entries:
        match = SEQUENCE_FILENAME.fullmatch(entry.name)
        if match:
            existing.add(int(match.group(1)))
            continue
        match = SEQUENCE_EXCLUSION_FILENAME.fullmatch(entry.name)
        if match:
            excluded.add(int(match.group(1)))
    return existing, excluded


def sequence_start_date_and_number():
    """Usa dhEmi para definir o inicio real da janela de um ano."""
    cutoff = (datetime.now().date() - timedelta(days=365)).isoformat()
    with connect_database() as connection:
        oldest = connection.execute(
            """
            SELECT MIN(issue_date) AS issue_date
            FROM items
            WHERE issue_date >= ?
              AND source_name GLOB '01001???????.xml'
              AND invoice_number GLOB '[0-9]*'
            """,
            (cutoff,),
        ).fetchone()
        if not oldest or not oldest["issue_date"]:
            return cutoff, None
        boundary = connection.execute(
            """
            SELECT MIN(CAST(invoice_number AS INTEGER)) AS invoice_number
            FROM items
            WHERE issue_date = ?
              AND source_name GLOB '01001???????.xml'
              AND invoice_number GLOB '[0-9]*'
            """,
            (oldest["issue_date"],),
        ).fetchone()
    return oldest["issue_date"], boundary["invoice_number"]


def find_missing_invoices(entries):
    existing, excluded = sequence_numbers(entries)
    if not existing:
        return [], "", None
    start_date, start_number = sequence_start_date_and_number()
    if start_number is None:
        return [], start_date, None
    end_number = max(existing)
    if start_number > end_number:
        return [], start_date, start_number
    missing = sorted(
        set(range(start_number, end_number + 1)) - existing - excluded
    )
    return missing, start_date, start_number


def _window_titles():
    if os.name != "nt":
        return []
    windows = []
    user32 = ctypes.windll.user32

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            windows.append((hwnd, buffer.value))
        return True

    user32.EnumWindows(callback, 0)
    return windows


def _find_window(title_fragment):
    fragment = title_fragment.casefold()
    for hwnd, title in _window_titles():
        if fragment in title.casefold():
            return hwnd, title
    return None, ""


def datasul_is_available():
    return _find_window("Datasul Interactive")[0] is not None


def _press_virtual_key(key, modifiers=()):
    user32 = ctypes.windll.user32
    for modifier in modifiers:
        user32.keybd_event(modifier, 0, 0, 0)
    user32.keybd_event(key, 0, 0, 0)
    user32.keybd_event(key, 0, 2, 0)
    for modifier in reversed(modifiers):
        user32.keybd_event(modifier, 0, 2, 0)
    time.sleep(0.08)


def _type_text(value):
    user32 = ctypes.windll.user32
    for character in str(value):
        key = user32.VkKeyScanW(ord(character))
        if key == -1:
            continue
        virtual_key = key & 0xFF
        shift_state = (key >> 8) & 0xFF
        modifiers = []
        if shift_state & 1:
            modifiers.append(0x10)
        if shift_state & 2:
            modifiers.append(0x11)
        if shift_state & 4:
            modifiers.append(0x12)
        _press_virtual_key(virtual_key, modifiers)


def _activate_window(hwnd):
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    # Um toque neutro em ALT permite que um processo em segundo plano assuma foco.
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    activated = bool(user32.SetForegroundWindow(hwnd))
    time.sleep(0.6)
    return activated or user32.GetForegroundWindow() == hwnd


def _wait_for_window(title_fragment, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd, title = _find_window(title_fragment)
        if hwnd:
            return hwnd, title
        time.sleep(0.5)
    return None, ""


def _wait_for_foreground_change(previous_hwnd, timeout=8):
    user32 = ctypes.windll.user32
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = user32.GetForegroundWindow()
        if current and current != previous_hwnd:
            return current
        time.sleep(0.2)
    return None


def _group_contiguous(numbers):
    if not numbers:
        return []
    ranges = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append((start, previous))
        start = previous = number
    ranges.append((start, previous))
    return ranges


def _record_recovery_attempt(numbers, result, message):
    now = datetime.now().isoformat(timespec="seconds")
    with connect_database() as connection:
        connection.executemany(
            """
            INSERT INTO recovery_attempts(
                invoice_number, attempted_at, result, message
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(invoice_number) DO UPDATE SET
                attempted_at = excluded.attempted_at,
                result = excluded.result,
                message = excluded.message
            """,
            [(number, now, result, message) for number in numbers],
        )


def _unattempted_missing(missing, force=False):
    if force:
        return missing
    with connect_database() as connection:
        attempted = {
            row["invoice_number"]
            for row in connection.execute(
                "SELECT invoice_number FROM recovery_attempts"
            )
        }
    return [number for number in missing if number not in attempted]


def recover_invoice_range(first_number, last_number):
    old_report_hwnd, _ = _find_window("SPFT046")
    if old_report_hwnd:
        _activate_window(old_report_hwnd)
        _press_virtual_key(0x73, (0x12,))
        time.sleep(0.8)

    datasul_hwnd, _ = _find_window("Datasul Interactive")
    if not datasul_hwnd:
        raise RuntimeError("Datasul Interactive nao esta aberto")
    if not _activate_window(datasul_hwnd):
        raise RuntimeError("Nao foi possivel trazer o Datasul para frente")

    # Atalho informado para abrir o localizador de programas do Datasul.
    _press_virtual_key(ord("X"), (0x11,))
    if not _wait_for_foreground_change(datasul_hwnd):
        raise RuntimeError("A janela de comando do Datasul nao abriu com Ctrl+X")
    time.sleep(0.4)
    _type_text("SPFT046")
    _press_virtual_key(0x0D)

    report_hwnd, _ = _wait_for_window("SPFT046")
    if not report_hwnd:
        raise RuntimeError("A janela SPFT046 nao abriu")
    _activate_window(report_hwnd)

    _type_text("01")
    _press_virtual_key(0x09)
    _type_text("1")
    _press_virtual_key(0x09)
    _type_text(f"{first_number:07d}")
    _press_virtual_key(0x09)
    _type_text(f"{last_number:07d}")
    _press_virtual_key(0x09)
    _press_virtual_key(0x09)
    _press_virtual_key(0x0D)
    time.sleep(4)
    _activate_window(report_hwnd)
    _press_virtual_key(0x73, (0x12,))


def refresh_missing_state(share_path, entries=None):
    entries = entries if entries is not None else list_xml_entries(share_path)
    missing, start_date, _ = find_missing_invoices(entries)
    available = datasul_is_available()
    if not missing:
        message = f"Sequência conferida desde {start_date}"
    elif available:
        message = f"{len(missing)} nota(s) ainda não possuem XML na pasta"
    else:
        message = "Datasul Interactive fechado; recuperação automática indisponível"
    update_state(
        missing_invoices=[f"{number:06d}" for number in missing[:MISSING_INVOICE_LIMIT]],
        missing_total=len(missing),
        datasul_available=available,
        recovery_message=message,
    )
    return missing


def recover_missing_invoices(share_path, force=False):
    if not RECOVERY_LOCK.acquire(blocking=False):
        return
    update_state(recovery_running=True)
    try:
        entries = list_xml_entries(share_path)
        missing, _, _ = find_missing_invoices(entries)
        candidates = _unattempted_missing(missing, force=force)
        if not candidates:
            refresh_missing_state(share_path, entries)
            return
        if len(candidates) > MISSING_INVOICE_LIMIT:
            update_state(
                recovery_message=(
                    f"{len(candidates)} lacunas detectadas; recuperação automática "
                    "bloqueada para revisão"
                )
            )
            return
        if not datasul_is_available():
            refresh_missing_state(share_path, entries)
            return

        for first_number, last_number in _group_contiguous(candidates):
            numbers = list(range(first_number, last_number + 1))
            update_state(
                recovery_message=(
                    f"Recuperando NF {first_number:06d}"
                    if first_number == last_number
                    else f"Recuperando NFs {first_number:06d} a {last_number:06d}"
                )
            )
            try:
                print(
                    f"[DATASUL] Solicitando XML {first_number:06d}"
                    if first_number == last_number
                    else (
                        f"[DATASUL] Solicitando XMLs {first_number:06d} "
                        f"a {last_number:06d}"
                    )
                )
                recover_invoice_range(first_number, last_number)
                _record_recovery_attempt(numbers, "submitted", "Enviado ao SPFT046")
            except Exception as error:
                print(f"[DATASUL] Falha: {error}")
                _record_recovery_attempt(numbers, "error", str(error)[:300])
                update_state(recovery_message=str(error))
                break

        time.sleep(2)
        refresh_missing_state(share_path)
        start_scan(share_path)
    finally:
        update_state(recovery_running=False)
        RECOVERY_LOCK.release()


def start_missing_recovery(share_path, force=False):
    if state_snapshot()["recovery_running"]:
        return False
    thread = threading.Thread(
        target=recover_missing_invoices,
        args=(share_path, force),
        daemon=True,
        name="nfe-datasul-recovery",
    )
    thread.start()
    return True


def scan_share(share_path, force=False):
    if not SCAN_LOCK.acquire(blocking=False):
        return
    started = time.time()
    try:
        update_state(
            running=True,
            phase="listing",
            message="Lendo nomes dos XMLs na pasta de rede",
            files_processed=0,
            items_found=0,
            errors=0,
            started_at=datetime.now().isoformat(timespec="seconds"),
        )
        entries = list_xml_entries(share_path)
        update_state(files_total=len(entries))

        with connect_database() as connection:
            indexed = {
                row["path"]: (row["mtime_ns"], row["size"])
                for row in connection.execute(
                    "SELECT path, mtime_ns, size FROM files"
                )
            }

        pending = []
        for entry in entries:
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            signature = (stat.st_mtime_ns, stat.st_size)
            if force or indexed.get(entry.path) != signature:
                pending.append(entry)

        update_state(
            phase="parsing",
            message=(
                f"Processando {len(pending):,} XMLs novos ou alterados"
                if pending else "Índice já está atualizado"
            ),
            files_pending=len(pending),
        )

        processed = 0
        items_found = 0
        errors = 0
        batch = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_xml_entry, entry.path): entry
                for entry in pending
            }
            with connect_database() as connection:
                for future in as_completed(futures):
                    entry = futures[future]
                    try:
                        result = future.result()
                    except Exception as error:
                        result = {
                            "status": "error",
                            "items": [],
                            "error": str(error)[:500],
                        }

                    batch.append((entry, result))
                    processed += 1
                    items_found += len(result["items"])
                    if result["status"] == "error":
                        errors += 1

                    if len(batch) >= 100:
                        for batch_entry, batch_result in batch:
                            persist_result(connection, batch_entry, batch_result)
                        connection.commit()
                        batch.clear()

                    if processed % 25 == 0 or processed == len(pending):
                        update_state(
                            files_processed=processed,
                            items_found=items_found,
                            errors=errors,
                            message=f"Processados {processed:,} de {len(pending):,} XMLs",
                        )

                for batch_entry, batch_result in batch:
                    persist_result(connection, batch_entry, batch_result)
                connection.commit()

        elapsed = time.time() - started
        update_state(
            running=False,
            phase="done",
            message=f"Atualização concluída em {elapsed:.1f}s",
            files_processed=processed,
            items_found=items_found,
            errors=errors,
            last_scan=datetime.now().isoformat(timespec="seconds"),
        )
        missing = refresh_missing_state(share_path, entries)
        if missing and datasul_is_available():
            start_missing_recovery(share_path)
    except Exception as error:
        update_state(
            running=False,
            phase="error",
            message=f"Falha ao acessar os XMLs: {error}",
            errors=STATE.get("errors", 0) + 1,
        )
    finally:
        SCAN_LOCK.release()


def start_scan(share_path, force=False):
    if state_snapshot()["running"]:
        return False
    thread = threading.Thread(
        target=scan_share,
        args=(share_path, force),
        daemon=True,
        name="nfe-indexer",
    )
    thread.start()
    return True


def auto_refresh_loop(share_path, interval=AUTO_REFRESH_SECONDS):
    """Atualiza o indice periodicamente; o botao manual continua independente."""
    while True:
        time.sleep(interval)
        start_scan(share_path)


def query_items(params):
    manufacturer = params.get("manufacturer", ["Volkswagen"])[0]
    plant = params.get("plant", [""])[0]
    search = params.get("search", [""])[0].strip()
    date_from = params.get("date_from", [""])[0]
    date_to = params.get("date_to", [""])[0]
    try:
        page = max(1, int(params.get("page", ["1"])[0]))
    except ValueError:
        page = 1
    page_size = 100

    where = []
    values = []
    if manufacturer != "Todas montadoras":
        where.append("manufacturer = ?")
        values.append(manufacturer)
    if plant:
        where.append("plant = ?")
        values.append(plant)
    if search:
        where.append(
            "(product_code LIKE ? OR client_code LIKE ? "
            "OR REPLACE(REPLACE(REPLACE(REPLACE(client_code, '.', ''), '-', ''), ' ', ''), '/', '') LIKE ? "
            "OR invoice_number LIKE ? "
            "OR billing_number LIKE ? OR description LIKE ? OR order_number LIKE ?)"
        )
        like = f"%{search}%"
        normalized_search = re.sub(r"[^0-9A-Za-z]", "", search)
        normalized_like = f"%{normalized_search}%"
        values.extend([
            like, like, normalized_like, like, like, like, like,
        ])
    if date_from:
        where.append("issue_date >= ?")
        values.append(date_from)
    if date_to:
        where.append("issue_date <= ?")
        values.append(date_to)

    clause = " AND ".join(where) if where else "1 = 1"
    dedupe_clause = """
        i.id = (
            SELECT MAX(id) FROM items
            WHERE access_key = i.access_key
              AND n_item = i.n_item
              AND quantity = i.quantity
        )
    """
    offset = (page - 1) * page_size

    with connect_database() as connection:
        summary = connection.execute(
            f"""
            SELECT
                COUNT(*) AS item_count,
                COUNT(DISTINCT file_path) AS invoice_count,
                COALESCE(SUM(quantity), 0) AS total_quantity,
                MAX(issued_at) AS latest_issue
            FROM items AS i
            WHERE {clause} AND {dedupe_clause}
            """,
            values,
        ).fetchone()

        rows = connection.execute(
            f"""
            SELECT *
            FROM items AS i
            WHERE {clause} AND {dedupe_clause}
            ORDER BY issued_at DESC, invoice_number DESC, CAST(n_item AS INTEGER)
            LIMIT ? OFFSET ?
            """,
            values + [page_size, offset],
        ).fetchall()

        if manufacturer == "Todas montadoras":
            plants = []
        else:
            plants = [
                row["plant"]
                for row in connection.execute(
                    "SELECT DISTINCT plant FROM items "
                    "WHERE manufacturer = ? ORDER BY plant",
                    (manufacturer,),
                )
            ]

    total = summary["item_count"]
    return {
        "items": [dict(row) for row in rows],
        "summary": dict(summary),
        "plants": plants,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


def query_deliveries(params):
    month = params.get("month", [datetime.now().strftime("%Y-%m")])[0]
    manufacturer = params.get("manufacturer", ["Todas montadoras"])[0]
    plant = params.get("plant", [""])[0]
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("Mes invalido")

    where = ["issue_date LIKE ?", "manufacturer != 'Nao classificado'"]
    values = [f"{month}-%"]
    if manufacturer != "Todas montadoras":
        where.append("manufacturer = ?")
        values.append(manufacturer)
    if plant:
        where.append("plant = ?")
        values.append(plant)
    clause = " AND ".join(where)

    with connect_database() as connection:
        deliveries = connection.execute(
            f"""
            SELECT manufacturer, plant, product_code, description, client_code,
                   commercial_unit, issue_date,
                   SUM(quantity) AS quantity,
                   GROUP_CONCAT(DISTINCT invoice_number) AS invoices
            FROM items
            WHERE {clause}
            GROUP BY manufacturer, plant, product_code, description, client_code,
                     commercial_unit, issue_date
            ORDER BY manufacturer, plant, product_code, issue_date
            """,
            values,
        ).fetchall()

        program_where = ["month = ?"]
        program_values = [month]
        if manufacturer != "Todas montadoras":
            program_where.append("manufacturer = ?")
            program_values.append(manufacturer)
        if plant:
            program_where.append("plant = ?")
            program_values.append(plant)
        programs = connection.execute(
            f"""
            SELECT manufacturer, plant, product_code, quantity
            FROM delivery_programs
            WHERE {" AND ".join(program_where)}
            """,
            program_values,
        ).fetchall()

        manufacturers = [
            row[0] for row in connection.execute(
                "SELECT DISTINCT manufacturer FROM items "
                "WHERE manufacturer != 'Nao classificado' ORDER BY manufacturer"
            )
        ]
        plant_values = [
            row[0] for row in connection.execute(
                "SELECT DISTINCT plant FROM items "
                "WHERE (? = 'Todas montadoras' OR manufacturer = ?) "
                "ORDER BY plant",
                (manufacturer, manufacturer),
            )
        ]

    row_map = {}
    for delivery in deliveries:
        key = (
            delivery["manufacturer"],
            delivery["plant"],
            delivery["product_code"],
        )
        row = row_map.setdefault(key, {
            "manufacturer": delivery["manufacturer"],
            "plant": delivery["plant"],
            "product_code": delivery["product_code"],
            "description": delivery["description"],
            "client_code": delivery["client_code"],
            "unit": delivery["commercial_unit"],
            "days": {},
            "total": 0.0,
            "program": 0.0,
        })
        quantity = delivery["quantity"] or 0
        day = int(delivery["issue_date"][-2:])
        row["days"][str(day)] = {
            "quantity": quantity,
            "invoices": (delivery["invoices"] or "").split(","),
        }
        row["total"] += quantity

    for program in programs:
        key = (
            program["manufacturer"],
            program["plant"],
            program["product_code"],
        )
        if key in row_map:
            row_map[key]["program"] = program["quantity"]

    rows = list(row_map.values())
    for row in rows:
        row["balance"] = row["program"] - row["total"]

    return {
        "month": month,
        "manufacturers": manufacturers,
        "plants": plant_values,
        "rows": rows,
    }


def is_admin_password(pin):
    """Confere a senha ADM sem nunca compará-la em texto aberto no codigo."""
    if not pin:
        return False
    if ADMIN_PASSWORD:
        return hmac.compare_digest(pin, ADMIN_PASSWORD)
    return verify_pin(pin, ADMIN_PASSWORD_FALLBACK_HASH)


def hash_pin(pin, salt=None):
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt_bytes, 200_000
    )
    return f"{salt_bytes.hex()}:{digest.hex()}"


def verify_pin(pin, stored):
    try:
        salt, expected = stored.split(":", 1)
    except ValueError:
        return False
    actual = hash_pin(pin, salt).split(":", 1)[1]
    return hmac.compare_digest(actual, expected)


def issue_auth_token(role, manufacturer):
    token = secrets.token_urlsafe(32)
    with AUTH_LOCK:
        now = time.time()
        expired = [
            key for key, value in AUTH_TOKENS.items()
            if value["expires_at"] <= now
        ]
        for key in expired:
            AUTH_TOKENS.pop(key, None)
        AUTH_TOKENS[token] = {
            "role": role,
            "manufacturer": manufacturer,
            "expires_at": now + AUTH_TOKEN_TTL_SECONDS,
        }
    return token


def validate_auth_token(token, manufacturer):
    if not token:
        return False
    with AUTH_LOCK:
        authorization = AUTH_TOKENS.get(token)
    return bool(
        authorization
        and authorization["expires_at"] > time.time()
        and hmac.compare_digest(
            authorization["manufacturer"], manufacturer
        )
    )


def validate_admin_token(token):
    if not token:
        return False
    with AUTH_LOCK:
        authorization = AUTH_TOKENS.get(token)
    return bool(
        authorization
        and authorization["expires_at"] > time.time()
        and authorization["role"] == "admin"
    )


def revoke_analyst_tokens(manufacturer=None):
    with AUTH_LOCK:
        revoked = [
            token
            for token, authorization in AUTH_TOKENS.items()
            if authorization["role"] == "analyst"
            and (
                manufacturer is None
                or authorization["manufacturer"] == manufacturer
            )
        ]
        for token in revoked:
            AUTH_TOKENS.pop(token, None)


def authorize_program_change(payload):
    pin = str(payload.get("pin", "")).strip()
    manufacturer = str(payload.get("manufacturer", "")).strip()
    if not manufacturer or manufacturer == "Todas montadoras":
        raise ValueError("Montadora invalida para autorizacao")
    if is_admin_password(pin):
        return {
            "authorized": True,
            "role": "admin",
            "registered": False,
            "manufacturer": manufacturer,
            "token": issue_auth_token("admin", manufacturer),
        }
    if not re.fullmatch(r"\d{6}", pin):
        raise ValueError("Informe a senha de analista com 6 digitos")

    with connect_database() as connection:
        setting_key = f"analyst_pin:{manufacturer}"
        row = connection.execute(
            "SELECT value FROM security_settings WHERE key = ?",
            (setting_key,),
        ).fetchone()
        if row is None:
            connection.execute(
                """
                INSERT INTO security_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (
                    setting_key,
                    hash_pin(pin),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            connection.commit()
            registered = True
        else:
            if not verify_pin(pin, row["value"]):
                raise ValueError("PIN incorreto")
            registered = False

    return {
        "authorized": True,
        "role": "analyst",
        "registered": registered,
        "manufacturer": manufacturer,
        "token": issue_auth_token("analyst", manufacturer),
    }


def manage_manufacturer_passwords(payload):
    token = str(payload.get("auth_token", ""))
    if not validate_admin_token(token):
        raise PermissionError("Acesso administrativo invalido ou expirado")
    action = str(payload.get("action", "list"))

    with connect_database() as connection:
        known_manufacturers = [
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT manufacturer
                FROM items
                WHERE manufacturer != 'Nao classificado'
                ORDER BY manufacturer
                """
            )
        ]

        if action == "list":
            configured = {
                row[0].split(":", 1)[1]
                for row in connection.execute(
                    """
                    SELECT key FROM security_settings
                    WHERE key LIKE 'analyst_pin:%'
                    """
                )
            }
            return {
                "manufacturers": [
                    {
                        "name": manufacturer,
                        "configured": manufacturer in configured,
                    }
                    for manufacturer in known_manufacturers
                ]
            }

        manufacturer = str(payload.get("manufacturer", "")).strip()
        if action in {"set", "clear"} and manufacturer not in known_manufacturers:
            raise ValueError("Montadora invalida")

        if action == "set":
            new_pin = str(payload.get("new_pin", "")).strip()
            if is_admin_password(new_pin):
                raise ValueError(
                    "A senha da montadora deve ser diferente da senha ADM"
                )
            if not re.fullmatch(r"\d{6}", new_pin):
                raise ValueError("A nova senha deve ter 6 digitos")
            connection.execute(
                """
                INSERT INTO security_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (
                    f"analyst_pin:{manufacturer}",
                    hash_pin(new_pin),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            connection.commit()
            revoke_analyst_tokens(manufacturer)
            return {
                "success": True,
                "message": f"Senha de {manufacturer} atualizada",
            }

        if action == "clear":
            connection.execute(
                "DELETE FROM security_settings WHERE key = ?",
                (f"analyst_pin:{manufacturer}",),
            )
            connection.commit()
            revoke_analyst_tokens(manufacturer)
            return {
                "success": True,
                "message": f"Senha de {manufacturer} removida",
            }

        if action == "clear_all":
            connection.execute(
                "DELETE FROM security_settings WHERE key LIKE 'analyst_pin:%'"
            )
            connection.commit()
            revoke_analyst_tokens()
            return {
                "success": True,
                "message": "Todas as senhas de montadoras foram removidas",
            }

    raise ValueError("Acao administrativa invalida")


def save_delivery_program(payload):
    month = str(payload.get("month", ""))
    manufacturer = str(payload.get("manufacturer", "")).strip()
    plant = str(payload.get("plant", "")).strip()
    product_code = str(payload.get("product_code", "")).strip()
    quantity = decimal_number(payload.get("quantity", 0))
    if not validate_auth_token(
        str(payload.get("auth_token", "")), manufacturer
    ):
        raise PermissionError(
            "Autorizacao ausente, expirada ou de outra montadora"
        )
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("Mes invalido")
    if not manufacturer or not plant or not product_code:
        raise ValueError("Montadora, planta e item sao obrigatorios")

    with connect_database() as connection:
        connection.execute(
            """
            INSERT INTO delivery_programs(
                month, manufacturer, plant, product_code, quantity, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(month, manufacturer, plant, product_code)
            DO UPDATE SET quantity = excluded.quantity,
                          updated_at = excluded.updated_at
            """,
            (
                month, manufacturer, plant, product_code, quantity,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
    return {"saved": True, "quantity": quantity}


def query_auxiliary_files(params):
    status = params.get("status", ["cancelled"])[0]
    if status not in {"cancelled", "correction"}:
        raise ValueError("Categoria de arquivo invalida")
    search = params.get("search", [""])[0].strip()
    try:
        page = max(1, int(params.get("page", ["1"])[0]))
    except ValueError:
        page = 1
    page_size = 100
    where = ["status = ?"]
    values = [status]
    if search:
        where.append("path LIKE ?")
        values.append(f"%{search}%")
    clause = " AND ".join(where)
    offset = (page - 1) * page_size

    with connect_database() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM files WHERE {clause}", values
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT path, size, processed_at
            FROM files
            WHERE {clause}
            ORDER BY processed_at DESC, path DESC
            LIMIT ? OFFSET ?
            """,
            values + [page_size, offset],
        ).fetchall()

    files = []
    for row in rows:
        files.append({
            "name": os.path.basename(row["path"]),
            "path": row["path"],
            "size": row["size"],
            "processed_at": row["processed_at"],
        })
    return {
        "files": files,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


class NFeHandler(SimpleHTTPRequestHandler):
    server_version = "NFeMonitor/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def translate_path(self, path):
        parsed_path = unquote(urlparse(path).path)
        if parsed_path.startswith("/assets/"):
            filename = os.path.basename(parsed_path)
            return str(APP_DIR / "assets" / filename)
        return super().translate_path(path)

    def log_message(self, fmt, *args):
        print(f"[HTTP] {self.address_string()} - {fmt % args}")

    def end_headers(self):
        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate, max-age=0",
        )
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            payload = state_snapshot()
            with connect_database() as connection:
                totals = connection.execute("""
                    SELECT
                        COUNT(*) AS indexed_files,
                        SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END)
                            AS accepted_files,
                        SUM(CASE WHEN status = 'ignored' THEN 1 ELSE 0 END)
                            AS ignored_files,
                        SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END)
                            AS error_files,
                        SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END)
                            AS cancelled_files,
                        SUM(CASE WHEN status = 'correction' THEN 1 ELSE 0 END)
                            AS correction_files
                    FROM files
                """).fetchone()
            payload["index"] = dict(totals)
            self.send_json(payload)
            return

        if parsed.path == "/api/items":
            try:
                self.send_json(query_items(parse_qs(parsed.query)))
            except Exception as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if parsed.path == "/api/files":
            try:
                self.send_json(query_auxiliary_files(parse_qs(parsed.query)))
            except Exception as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.BAD_REQUEST,
                )
            return

        if parsed.path == "/api/deliveries":
            try:
                self.send_json(query_deliveries(parse_qs(parsed.query)))
            except Exception as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.BAD_REQUEST,
                )
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/refresh":
            started = start_scan(self.server.share_path)
            self.send_json(
                {"started": started, "status": state_snapshot()},
                status=HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT,
            )
            return

        if parsed.path == "/api/recover-missing":
            started = start_missing_recovery(self.server.share_path, force=True)
            self.send_json(
                {"started": started, "status": state_snapshot()},
                status=HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT,
            )
            return

        if parsed.path == "/api/delivery-program":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length) or b"{}")
                self.send_json(save_delivery_program(payload))
            except PermissionError as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.FORBIDDEN,
                )
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.BAD_REQUEST,
                )
            return

        if parsed.path == "/api/program-auth":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length) or b"{}")
                self.send_json(authorize_program_change(payload))
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.UNAUTHORIZED,
                )
            return

        if parsed.path == "/api/admin-passwords":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length) or b"{}")
                self.send_json(manage_manufacturer_passwords(payload))
            except PermissionError as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.FORBIDDEN,
                )
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(
                    {"error": str(error)},
                    status=HTTPStatus.BAD_REQUEST,
                )
            return

        self.send_json({"error": "Endpoint nao encontrado"}, HTTPStatus.NOT_FOUND)


def run_server(host, port, share_path):
    initialize_database()
    server = ThreadingHTTPServer((host, port), NFeHandler)
    server.share_path = share_path
    start_scan(share_path)
    threading.Thread(
        target=auto_refresh_loop,
        args=(share_path,),
        daemon=True,
        name="nfe-auto-refresh",
    ).start()
    print("=" * 68)
    print("MONITOR NF-e - MONTADORAS")
    print(f"Pasta XML: {share_path}")
    print(f"Acesso local: http://localhost:{port}")
    print(f"Acesso na rede: http://{local_network_ip()}:{port}")
    print("Atualizacao automatica: a cada 5 minutos")
    print("=" * 68)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando servidor...")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor local de XMLs NF-e")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--share", default=DEFAULT_SHARE)
    arguments = parser.parse_args()
    run_server(arguments.host, arguments.port, arguments.share)
