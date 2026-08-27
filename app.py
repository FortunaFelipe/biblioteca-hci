from __future__ import annotations

import csv
import hmac
import html
import io
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent
# Caminho do banco configurável por variável de ambiente, para apontar
# para um disco persistente quando publicado (ex.: /var/data/biblioteca.db).
DB_PATH = Path(os.environ.get("BIBLIOTECA_DB", str(APP_DIR / "data" / "biblioteca.db")))
DATA_DIR = DB_PATH.parent

PAGE_DASHBOARD = "Visão geral"
PAGE_NEW_LOAN = "Registrar empréstimo"
PAGE_RETURN = "Registrar devolução"
PAGE_BOOKS = "Acervo"
PAGE_HISTORY = "Histórico"
PAGES = [PAGE_DASHBOARD, PAGE_NEW_LOAN, PAGE_RETURN, PAGE_BOOKS, PAGE_HISTORY]


st.set_page_config(
    page_title="Biblioteca HCI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


@contextmanager
def connect_db():
    database_url = get_setting("TURSO_DATABASE_URL")
    auth_token = get_setting("TURSO_AUTH_TOKEN")

    if database_url or auth_token:
        if not database_url or not auth_token:
            raise RuntimeError(
                "Configure TURSO_DATABASE_URL e TURSO_AUTH_TOKEN em conjunto."
            )
        try:
            import libsql
        except ImportError as exc:
            raise RuntimeError(
                "A conexão em nuvem exige a dependência 'libsql'."
            ) from exc
        conn = libsql.connect(database=database_url, auth_token=auth_token)
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                month_label TEXT,
                year INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS collaborators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                department TEXT,
                email TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                collaborator_id INTEGER NOT NULL,
                checkout_date TEXT NOT NULL,
                return_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books (id),
                FOREIGN KEY (collaborator_id) REFERENCES collaborators (id)
            );

            CREATE INDEX IF NOT EXISTS idx_loans_book_open
                ON loans (book_id, return_date);
            CREATE INDEX IF NOT EXISTS idx_loans_collaborator
                ON loans (collaborator_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_loan_per_book
                ON loans (book_id)
                WHERE return_date IS NULL;
            """
        )


def run_query(query: str, params: tuple = ()) -> list[sqlite3.Row | dict]:
    with connect_db() as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        if not rows or isinstance(rows[0], sqlite3.Row):
            return rows

        columns = [column[0] for column in cursor.description or ()]
        return [dict(zip(columns, row)) for row in rows]


def run_command(query: str, params: tuple = ()) -> None:
    with connect_db() as conn:
        conn.execute(query, params)


def today_iso() -> str:
    return date.today().isoformat()


def parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def days_between(start: str, end: str | None = None) -> int:
    start_date = parse_iso(start)
    end_date = parse_iso(end) or date.today()
    if not start_date:
        return 0
    return max((end_date - start_date).days, 0)


def month_options() -> list[str]:
    return [
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]


def active_loans() -> list[sqlite3.Row]:
    return run_query(
        """
        SELECT
            loans.id,
            loans.checkout_date,
            loans.notes,
            books.title,
            books.author,
            collaborators.name
        FROM loans
        JOIN books ON books.id = loans.book_id
        JOIN collaborators ON collaborators.id = loans.collaborator_id
        WHERE loans.return_date IS NULL
        ORDER BY loans.checkout_date ASC, books.title ASC
        """
    )


def loan_history() -> list[sqlite3.Row]:
    return run_query(
        """
        SELECT
            loans.id,
            loans.checkout_date,
            loans.return_date,
            loans.notes,
            books.title,
            books.author,
            collaborators.name
        FROM loans
        JOIN books ON books.id = loans.book_id
        JOIN collaborators ON collaborators.id = loans.collaborator_id
        ORDER BY COALESCE(loans.return_date, loans.checkout_date) DESC, loans.id DESC
        """
    )


def available_books() -> list[sqlite3.Row]:
    return run_query(
        """
        SELECT books.*
        FROM books
        WHERE books.is_active = 1
          AND NOT EXISTS (
              SELECT 1
              FROM loans
              WHERE loans.book_id = books.id
                AND loans.return_date IS NULL
          )
        ORDER BY books.title ASC
        """
    )


def active_books() -> list[sqlite3.Row]:
    return run_query(
        """
        SELECT
            books.*,
            CASE WHEN open_loans.id IS NULL THEN 'Disponível' ELSE 'Emprestado' END AS status,
            collaborators.name AS borrower,
            open_loans.checkout_date
        FROM books
        LEFT JOIN loans AS open_loans
            ON open_loans.book_id = books.id
           AND open_loans.return_date IS NULL
        LEFT JOIN collaborators
            ON collaborators.id = open_loans.collaborator_id
        WHERE books.is_active = 1
        ORDER BY books.title ASC
        """
    )


def get_or_create_collaborator(name: str) -> int:
    normalized_name = " ".join(name.split())
    with connect_db() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM collaborators
            WHERE lower(name) = lower(?)
              AND is_active = 1
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_name,),
        ).fetchone()
        if existing:
            collaborator_id = existing["id"] if isinstance(existing, sqlite3.Row) else existing[0]
            return int(collaborator_id)

        cursor = conn.execute(
            "INSERT INTO collaborators (name) VALUES (?)",
            (normalized_name,),
        )
        return int(cursor.lastrowid)


def to_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _brand_pattern(stroke_opacity: str) -> str:
    """Elemento gráfico do Brandbook (arco dourado + losangos) como SVG inline."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120' viewBox='0 0 120 120'>"
        "<g fill='none' stroke='#e0ad55' stroke-width='1.1' stroke-opacity='" + stroke_opacity + "'>"
        "<path d='M-50 78 Q0 40 50 78'/>"
        "<path d='M10 78 Q60 40 110 78'/>"
        "<path d='M70 78 Q120 40 170 78'/>"
        "<rect x='48' y='6' width='20' height='20' transform='rotate(45 58 16)'/>"
        "<rect x='48' y='96' width='20' height='20' transform='rotate(45 58 106)'/>"
        "</g></svg>"
    )
    encoded = (
        svg.replace("<", "%3C").replace(">", "%3E").replace("#", "%23").replace(" ", "%20")
    )
    return 'url("data:image/svg+xml,' + encoded + '")'


def inject_styles() -> None:
    css = """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@300;400;500;600;700;800&display=swap');

            :root {
                --hci-blue: #182845;
                --hci-blue-soft: #233757;
                --hci-gold: #e0ad55;
                --hci-gold-pale: #f8eedc;
                --hci-slate: #5f657f;
                --hci-gray: #dbdbdb;
                --hci-canvas: #f5f6f8;
                --hci-white: #ffffff;
                --hci-ink: #182845;
                --line: rgba(24, 40, 69, .11);
                --line-strong: rgba(24, 40, 69, .2);
                --shadow-soft: 0 14px 38px rgba(24, 40, 69, .07);
                --shadow-lift: 0 18px 44px rgba(24, 40, 69, .12);
                --radius-xl: 22px;
                --radius-lg: 16px;
                --radius-md: 12px;
                --radius-sm: 9px;
            }

            html, body, [class*="css"],
            button, input, textarea, select {
                font-family: "Red Hat Display", sans-serif;
            }

            html, body {
                font-size: 16px;
            }

            .stApp {
                color: var(--hci-ink);
                background:
                    radial-gradient(circle at 88% -8%, rgba(224, 173, 85, .13), transparent 28rem),
                    var(--hci-canvas);
            }

            [data-testid="stHeader"] {
                background: transparent;
            }

            [data-testid="stAppViewContainer"] > .main .block-container {
                width: min(100%, 1320px);
                padding: 2.2rem 2.6rem 4rem;
            }

            #MainMenu, footer {
                visibility: hidden;
            }

            h1, h2, h3 {
                font-family: "Red Hat Display", sans-serif;
                letter-spacing: -.025em;
                color: var(--hci-blue);
            }

            p, label, [data-testid="stCaptionContainer"] {
                letter-spacing: .005em;
            }

            /* Barra lateral: navegação enxuta para a pessoa responsável. */
            [data-testid="stSidebar"] {
                background:
                    linear-gradient(180deg, rgba(24, 40, 69, .96), rgba(24, 40, 69, .99)),
                    __PATTERN_SIDEBAR__ 0 0 / 150px 150px;
                border-right: 1px solid rgba(224, 173, 85, .22);
            }

            [data-testid="stSidebar"] > div:first-child {
                padding: 1.55rem 1.15rem 1.25rem;
            }

            [data-testid="stSidebar"] h1,
            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] span {
                color: #ffffff;
            }

            [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
            [data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {
                color: rgba(255, 255, 255, .62);
            }

            [data-testid="stSidebar"] [role="radiogroup"] {
                gap: .3rem;
                margin-top: .35rem;
            }

            [data-testid="stSidebar"] [role="radiogroup"] label {
                position: relative;
                border-radius: var(--radius-sm);
                padding: .62rem .75rem;
                margin: 0;
                transition: background .18s ease, transform .18s ease;
            }

            [data-testid="stSidebar"] [role="radiogroup"] label:hover {
                background: rgba(255, 255, 255, .08);
                transform: translateX(2px);
            }

            [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
                background: rgba(224, 173, 85, .14);
                box-shadow: inset 2px 0 0 var(--hci-gold);
            }

            [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
                font-weight: 650;
            }

            .sidebar-brand {
                padding: .15rem .25rem 1.15rem;
                margin-bottom: 1.05rem;
                border-bottom: 1px solid rgba(255, 255, 255, .13);
            }

            .sidebar-mark {
                display: block;
                height: 1.9rem;
                width: auto;
            }

            .sidebar-sub {
                margin: .28rem 0 0 .14rem;
                color: rgba(255, 255, 255, .8);
                font-size: .58rem;
                font-weight: 400;
                letter-spacing: .37rem;
            }

            .sidebar-title {
                position: relative;
                margin-top: 1.2rem;
                padding-bottom: .62rem;
                color: #ffffff;
                font-size: 1.12rem;
                font-weight: 650;
            }

            .sidebar-title::after {
                content: "";
                position: absolute;
                left: 0;
                bottom: 0;
                width: 2.6rem;
                height: 2px;
                background: var(--hci-gold);
            }

            .sidebar-tagline {
                margin-top: .62rem;
                color: rgba(255, 255, 255, .62);
                font-size: .8rem;
            }

            .sidebar-status {
                display: flex;
                gap: .6rem;
                align-items: center;
                margin: .9rem .1rem .15rem;
                padding: .75rem .8rem;
                color: rgba(255, 255, 255, .72);
                background: rgba(255, 255, 255, .055);
                border: 1px solid rgba(255, 255, 255, .1);
                border-radius: var(--radius-sm);
                font-size: .74rem;
                line-height: 1.3;
            }

            .sidebar-status-dot {
                width: .48rem;
                height: .48rem;
                flex: 0 0 auto;
                border-radius: 50%;
                background: var(--hci-gold);
                box-shadow: 0 0 0 4px rgba(224, 173, 85, .12);
            }

            /* Cabeçalho editorial. */
            .app-topbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                margin-bottom: 2rem;
                padding-bottom: 1.1rem;
                border-bottom: 1px solid var(--line);
            }

            .topbar-brand {
                display: flex;
                align-items: center;
                gap: .8rem;
                color: var(--hci-blue);
            }

            .topbar-mark {
                width: 3.1rem;
                height: auto;
            }

            .topbar-wording strong {
                display: block;
                font-size: .9rem;
                font-weight: 700;
                letter-spacing: .02em;
            }

            .topbar-wording span {
                display: block;
                margin-top: .1rem;
                color: var(--hci-slate);
                font-size: .72rem;
            }

            .topbar-date {
                color: var(--hci-slate);
                font-size: .78rem;
                font-weight: 500;
                text-align: right;
            }

            .page-intro {
                position: relative;
                overflow: hidden;
                margin-bottom: 1.65rem;
                padding: 2rem 2.2rem 2.1rem;
                color: #ffffff;
                background: var(--hci-blue);
                border: 1px solid rgba(24, 40, 69, .1);
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-lift);
                animation: hci-rise .38s ease-out both;
            }

            .page-intro::after {
                content: "";
                position: absolute;
                inset: 0;
                pointer-events: none;
                background: __PATTERN_HERO__ 0 0 / 138px 138px;
                opacity: .78;
                -webkit-mask-image: linear-gradient(90deg, transparent 42%, #000 100%);
                mask-image: linear-gradient(90deg, transparent 42%, #000 100%);
            }

            .page-eyebrow {
                position: relative;
                z-index: 1;
                margin-bottom: .7rem;
                color: var(--hci-gold);
                font-size: .69rem;
                font-weight: 700;
                letter-spacing: .18em;
                text-transform: uppercase;
            }

            .page-intro h1 {
                position: relative;
                z-index: 1;
                max-width: 760px;
                margin: 0;
                color: #ffffff;
                font-size: clamp(2rem, 4vw, 3.3rem);
                font-weight: 400;
                letter-spacing: -.045em;
                line-height: 1.02;
            }

            .page-intro p {
                position: relative;
                z-index: 1;
                max-width: 690px;
                margin: .9rem 0 0;
                color: rgba(255, 255, 255, .72);
                font-size: 1rem;
                line-height: 1.55;
            }

            .page-intro-accent {
                position: absolute;
                z-index: 1;
                left: 2.2rem;
                bottom: 0;
                width: 5.2rem;
                height: 3px;
                background: var(--hci-gold);
            }

            @keyframes hci-rise {
                from { opacity: 0; transform: translateY(8px); }
                to { opacity: 1; transform: translateY(0); }
            }

            /* Indicadores: números em destaque, sem aparência de painel genérico. */
            .hci-metric {
                min-height: 132px;
                position: relative;
                overflow: hidden;
                padding: 1.15rem 1.2rem 1rem;
                background: #ffffff;
                border: 1px solid var(--line);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-soft);
                transition: transform .18s ease, box-shadow .18s ease;
            }

            .hci-metric:hover {
                transform: translateY(-2px);
                box-shadow: var(--shadow-lift);
            }

            .hci-metric::before {
                content: "";
                position: absolute;
                left: 1.2rem;
                right: 1.2rem;
                top: 0;
                height: 3px;
                background: var(--hci-gold);
            }

            .hci-metric-label {
                margin-top: .25rem;
                color: var(--hci-slate);
                font-size: .78rem;
                font-weight: 600;
            }

            .hci-metric-value {
                margin-top: .55rem;
                color: var(--hci-blue);
                font-size: 2.15rem;
                font-weight: 500;
                line-height: 1;
                letter-spacing: -.045em;
            }

            .hci-metric-note {
                margin-top: .55rem;
                color: rgba(95, 101, 127, .8);
                font-size: .7rem;
            }

            /* Títulos de seção e blocos de apoio. */
            .hci-section {
                display: flex;
                align-items: end;
                justify-content: space-between;
                gap: 1rem;
                margin: 2rem 0 .9rem;
            }

            .hci-section h2 {
                position: relative;
                margin: 0;
                padding: 0 0 .55rem 1rem;
                color: var(--hci-blue);
                font-size: 1.28rem;
                font-weight: 600;
                letter-spacing: -.02em;
            }

            .hci-section h2::before {
                content: "";
                position: absolute;
                left: 0;
                top: .12rem;
                width: 3px;
                height: 1.35rem;
                background: var(--hci-gold);
            }

            .helper-card {
                height: 100%;
                min-height: 255px;
                padding: 1.45rem;
                color: #ffffff;
                background:
                    linear-gradient(180deg, rgba(24, 40, 69, .96), rgba(24, 40, 69, .99)),
                    __PATTERN_CARD__ 0 0 / 130px 130px;
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-soft);
            }

            .helper-kicker {
                color: var(--hci-gold);
                font-size: .68rem;
                font-weight: 700;
                letter-spacing: .16em;
                text-transform: uppercase;
            }

            .helper-card h3 {
                margin: .8rem 0 .65rem;
                color: #ffffff;
                font-size: 1.38rem;
                font-weight: 500;
                line-height: 1.15;
            }

            .helper-card p {
                margin: 0;
                color: rgba(255, 255, 255, .68);
                font-size: .86rem;
                line-height: 1.55;
            }

            .helper-list {
                margin: 1.1rem 0 0;
                padding: 0;
                list-style: none;
                counter-reset: item;
            }

            .helper-list li {
                display: flex;
                gap: .65rem;
                align-items: flex-start;
                margin-top: .72rem;
                color: rgba(255, 255, 255, .82);
                font-size: .78rem;
                line-height: 1.4;
            }

            .helper-list li::before {
                counter-increment: item;
                content: counter(item, decimal-leading-zero);
                color: var(--hci-gold);
                font-size: .65rem;
                font-weight: 700;
                letter-spacing: .04em;
            }

            .empty-state {
                padding: 2.4rem 1.5rem;
                text-align: center;
                background: rgba(255, 255, 255, .72);
                border: 1px dashed var(--line-strong);
                border-radius: var(--radius-lg);
            }

            .empty-state strong {
                display: block;
                color: var(--hci-blue);
                font-size: 1rem;
            }

            .empty-state span {
                display: block;
                max-width: 440px;
                margin: .35rem auto 0;
                color: var(--hci-slate);
                font-size: .82rem;
            }

            .summary-line {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                margin: .25rem 0 .75rem;
                color: var(--hci-slate);
                font-size: .76rem;
            }

            .summary-pill {
                display: inline-flex;
                align-items: center;
                gap: .42rem;
                padding: .35rem .58rem;
                color: var(--hci-blue);
                background: var(--hci-gold-pale);
                border-radius: 999px;
                font-weight: 650;
            }

            .summary-pill::before {
                content: "";
                width: .4rem;
                height: .4rem;
                border-radius: 50%;
                background: var(--hci-gold);
            }

            /* Componentes nativos harmonizados com a marca. */
            div[data-testid="stDataFrame"] {
                border: 1px solid var(--line);
                border-radius: var(--radius-md);
                overflow: hidden;
                box-shadow: 0 8px 24px rgba(24, 40, 69, .045);
            }

            [data-testid="stForm"] {
                padding: 1.35rem 1.35rem .5rem;
                background: rgba(255, 255, 255, .9);
                border: 1px solid var(--line);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-soft);
            }

            .stButton > button,
            .stDownloadButton > button,
            .stFormSubmitButton > button {
                min-height: 2.7rem;
                border-radius: var(--radius-sm);
                border: 1px solid var(--line-strong);
                font-weight: 650;
                color: var(--hci-blue);
                background: #ffffff;
                transition: border-color .16s ease, background .16s ease, color .16s ease, transform .16s ease;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover,
            .stFormSubmitButton > button:hover {
                border-color: var(--hci-gold);
                color: var(--hci-blue);
                transform: translateY(-1px);
            }

            .stButton > button[kind="primary"],
            .stFormSubmitButton > button[kind="primary"],
            button[data-testid="baseButton-primary"] {
                background: var(--hci-blue);
                border-color: var(--hci-blue);
                color: #ffffff;
            }

            .stButton > button[kind="primary"]:hover,
            .stFormSubmitButton > button[kind="primary"]:hover,
            button[data-testid="baseButton-primary"]:hover {
                background: var(--hci-blue-soft);
                border-color: var(--hci-gold);
                color: #ffffff;
            }

            .stTextInput input,
            .stTextArea textarea,
            .stNumberInput input,
            .stDateInput input,
            .stSelectbox div[data-baseweb="select"] > div {
                border-radius: var(--radius-sm);
                border-color: var(--line-strong);
                background: #ffffff;
            }

            .stAlert {
                border-radius: var(--radius-md);
            }

            [data-testid="stExpander"] {
                border: 1px solid var(--line);
                border-radius: var(--radius-lg);
                background: rgba(255, 255, 255, .74);
                box-shadow: 0 8px 24px rgba(24, 40, 69, .035);
            }

            [data-testid="stExpander"] summary {
                font-weight: 650;
                color: var(--hci-blue);
            }

            [data-testid="stSidebar"] .stDownloadButton > button {
                min-height: 2.45rem;
                color: #ffffff;
                background: transparent;
                border-color: rgba(255, 255, 255, .22);
                font-size: .76rem;
            }

            [data-testid="stSidebar"] .stDownloadButton > button:hover {
                color: #ffffff;
                background: rgba(255, 255, 255, .07);
                border-color: var(--hci-gold);
            }

            .login-wrap {
                max-width: 760px;
                margin: 3.5rem auto 1rem;
                padding: 2.5rem;
                color: #ffffff;
                background: var(--hci-blue);
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-lift);
            }

            .login-wrap h1 {
                margin: 1.2rem 0 .5rem;
                color: #ffffff;
                font-size: 2.1rem;
                font-weight: 400;
            }

            .login-wrap p {
                color: rgba(255, 255, 255, .68);
            }

            @media (max-width: 900px) {
                [data-testid="stAppViewContainer"] > .main .block-container {
                    padding: 1.4rem 1.15rem 3rem;
                }

                .page-intro {
                    padding: 1.6rem 1.45rem 1.75rem;
                    border-radius: var(--radius-lg);
                }

                .page-intro-accent {
                    left: 1.45rem;
                }

                .hci-metric {
                    min-height: 116px;
                    margin-bottom: .4rem;
                }

                .app-topbar {
                    margin-bottom: 1.35rem;
                }
            }
        </style>
    """
    css = css.replace("__PATTERN_SIDEBAR__", _brand_pattern("0.15"))
    css = css.replace("__PATTERN_HERO__", _brand_pattern("0.52"))
    css = css.replace("__PATTERN_CARD__", _brand_pattern("0.22"))
    st.markdown(css, unsafe_allow_html=True)


def section_title(text: str) -> None:
    """Cabeçalho de seção com o traço dourado de acento do Brandbook."""
    st.markdown(f'<div class="hci-section"><h2>{text}</h2></div>', unsafe_allow_html=True)


def brand_mark(css_class: str, main_color: str, gold_color: str = "#e0ad55") -> str:
    """Wordmark 'hci' do Brandbook: c aberto com o arco dourado e o i pontuado."""
    return (
        f'<svg class="{css_class}" viewBox="0 0 116 72" fill="none" '
        'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="hci advisors">'
        f'<g stroke="{main_color}" stroke-width="3" stroke-linecap="round" '
        'stroke-linejoin="round" fill="none">'
        '<path d="M10 8 V64 M10 42 C10 30 34 30 34 42 V64"/>'
        '<path d="M73.5 36.4 A15 15 0 1 0 73.5 55.6"/>'
        '<path d="M96 30 V64"/>'
        '</g>'
        f'<circle cx="96" cy="20" r="3.1" fill="{main_color}"/>'
        f'<path d="M49 31 Q61.5 22 74 29" stroke="{gold_color}" stroke-width="3" '
        'stroke-linecap="round" fill="none"/>'
        '</svg>'
    )


def date_long_pt(value: date) -> str:
    months = [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    return f"{value.day} de {months[value.month - 1]} de {value.year}"


def render_header(page: str) -> None:
    page_content = {
        PAGE_DASHBOARD: (
            "Biblioteca interna",
            "Onde estão os livros",
            "Uma visão direta do acervo: o que está disponível, o que saiu e com quem está cada exemplar.",
        ),
        PAGE_NEW_LOAN: (
            "Nova movimentação",
            "Registrar empréstimo",
            "Selecione o livro e informe somente o nome completo de quem está levando o exemplar.",
        ),
        PAGE_RETURN: (
            "Entrada no acervo",
            "Registrar devolução",
            "Encerre um empréstimo aberto e devolva o livro à lista de exemplares disponíveis.",
        ),
        PAGE_BOOKS: (
            "Catálogo interno",
            "Acervo da biblioteca",
            "Cadastre os títulos e consulte rapidamente a situação atual de cada livro.",
        ),
        PAGE_HISTORY: (
            "Registro de movimentações",
            "Histórico da biblioteca",
            "Consulte empréstimos e devoluções anteriores ou exporte os registros para CSV.",
        ),
    }
    eyebrow, title, description = page_content[page]
    st.markdown(
        f"""
        <div class="app-topbar">
            <div class="topbar-brand" aria-label="Biblioteca HCI Advisors">
                {brand_mark("topbar-mark", "#182845")}
                <div class="topbar-wording">
                    <strong>Biblioteca HCI</strong>
                    <span>Controle local do acervo</span>
                </div>
            </div>
            <div class="topbar-date">{date_long_pt(date.today())}</div>
        </div>
        <section class="page-intro">
            <div class="page-eyebrow">{eyebrow}</div>
            <h1>{title}</h1>
            <p>{description}</p>
            <span class="page-intro-accent"></span>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_metric(label: str, value: str | int, note: str) -> None:
    st.markdown(
        f"""
        <div class="hci-metric">
            <div class="hci-metric-label">{html.escape(label)}</div>
            <div class="hci-metric-value">{html.escape(str(value))}</div>
            <div class="hci-metric-note">{html.escape(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_helper(kicker: str, title: str, description: str, steps: list[str]) -> None:
    items = "".join(f"<li>{html.escape(step)}</li>" for step in steps)
    st.markdown(
        f"""
        <aside class="helper-card">
            <div class="helper-kicker">{html.escape(kicker)}</div>
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(description)}</p>
            <ol class="helper-list">{items}</ol>
        </aside>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="empty-state">
            <strong>{html.escape(title)}</strong>
            <span>{html.escape(description)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard() -> None:
    books = active_books()
    loans = active_loans()
    open_days = [days_between(row["checkout_date"]) for row in loans]
    available_count = len([book for book in books if book["status"] == "Disponível"])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric("Livros no acervo", len(books), "títulos ativos cadastrados")
    with col2:
        render_metric("Disponíveis", available_count, "prontos para empréstimo")
    with col3:
        render_metric("Com assessores", len(loans), "empréstimos em aberto")
    with col4:
        render_metric("Há mais tempo fora", f"{max(open_days) if open_days else 0} dias", "contagem desde a retirada")

    section_title("Empréstimos em aberto")
    if not loans:
        render_empty_state(
            "Todos os livros estão no acervo",
            "Quando um exemplar for retirado, o nome do assessor e a data aparecerão aqui.",
        )
        return

    st.markdown(
        f"""
        <div class="summary-line">
            <span>Acompanhamento atual do acervo</span>
            <span class="summary-pill">{len(loans)} {'livro' if len(loans) == 1 else 'livros'} fora</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    table = [
        {
            "Livro": row["title"],
            "Autor": row["author"] or "",
            "Com": row["name"],
            "Retirado em": parse_iso(row["checkout_date"]).strftime("%d/%m/%Y"),
            "Dias": days_between(row["checkout_date"]),
            "Observações": row["notes"] or "",
        }
        for row in loans
    ]
    st.dataframe(table, width="stretch", hide_index=True)


def render_new_loan() -> None:
    books = available_books()

    if not books:
        section_title("Dados do empréstimo")
        render_empty_state(
            "Não há livros disponíveis",
            "Cadastre um livro no acervo ou registre uma devolução antes de criar um novo empréstimo.",
        )
        return

    book_options = {
        f"{row['title']} — {row['author'] or 'Autor não informado'} · {int(row['id']):03d}": row["id"]
        for row in books
    }

    section_title("Dados do empréstimo")
    form_col, helper_col = st.columns([1.35, .8], gap="large")
    with form_col:
        with st.form("new_loan_form", clear_on_submit=True):
            book_label = st.selectbox("Livro disponível", list(book_options.keys()))
            collaborator_name = st.text_input(
                "Nome completo do assessor *",
                placeholder="Ex.: Maria da Silva",
            )
            checkout = st.date_input("Data da retirada", value=date.today(), format="DD/MM/YYYY")
            notes = st.text_area(
                "Observações",
                placeholder="Opcional: estado do exemplar ou outra informação útil.",
            )
            submitted = st.form_submit_button("Registrar empréstimo", type="primary", width="stretch")

    with helper_col:
        render_helper(
            "Fluxo simples",
            "Sem cadastro prévio",
            "O sistema reconhece nomes já utilizados e cria o registro interno automaticamente.",
            [
                "Selecione um livro disponível.",
                "Informe o nome completo do assessor.",
                "Confirme a data em que o livro saiu.",
            ],
        )

    if submitted:
        if not collaborator_name.strip():
            st.error("Informe o nome completo do assessor.")
            return

        collaborator_id = get_or_create_collaborator(collaborator_name)
        try:
            run_command(
                """
                INSERT INTO loans (book_id, collaborator_id, checkout_date, notes)
                VALUES (?, ?, ?, ?)
                """,
                (book_options[book_label], collaborator_id, checkout.isoformat(), notes.strip()),
            )
        except Exception as exc:
            if "unique constraint" not in str(exc).lower():
                raise
            st.error("Este livro acabou de ser emprestado por outra pessoa. Atualize a tela e escolha outro exemplar.")
            return
        st.success("Empréstimo registrado.")
        st.rerun()


def render_returns() -> None:
    loans = active_loans()
    section_title("Dados da devolução")
    if not loans:
        render_empty_state(
            "Nenhum empréstimo em aberto",
            "Todos os exemplares cadastrados estão disponíveis no acervo.",
        )
        return

    loan_options = {
        f"{row['title']} com {row['name']} desde {parse_iso(row['checkout_date']).strftime('%d/%m/%Y')} ({days_between(row['checkout_date'])} dias)": row[
            "id"
        ]
        for row in loans
    }

    form_col, helper_col = st.columns([1.35, .8], gap="large")
    with form_col:
        with st.form("return_form"):
            loan_label = st.selectbox("Empréstimo em aberto", list(loan_options.keys()))
            returned = st.date_input("Data da devolução", value=date.today(), format="DD/MM/YYYY")
            submitted = st.form_submit_button("Confirmar devolução", type="primary", width="stretch")

    with helper_col:
        render_helper(
            "Retorno ao acervo",
            "Uma confirmação",
            "Ao concluir, o empréstimo permanece no histórico e o livro volta a aparecer como disponível.",
            [
                "Localize o livro e o assessor.",
                "Confirme a data em que o livro voltou.",
                "Finalize para liberar o exemplar.",
            ],
        )

    if submitted:
        selected_loan_id = loan_options[loan_label]
        selected_loan = next(row for row in loans if row["id"] == selected_loan_id)
        checkout_date = parse_iso(selected_loan["checkout_date"])
        if checkout_date and returned < checkout_date:
            st.error("A data da devolução não pode ser anterior à data da retirada.")
            return

        run_command(
            """
            UPDATE loans
            SET return_date = ?
            WHERE id = ?
              AND return_date IS NULL
            """,
            (returned.isoformat(), selected_loan_id),
        )
        st.success("Devolução registrada.")
        st.rerun()


def render_books() -> None:
    rows = active_books()
    section_title("Cadastro e consulta")

    with st.expander("Adicionar livro ao acervo", expanded=not bool(rows)):
        with st.form("book_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            title = col1.text_input("Título do livro *", placeholder="Digite o título completo")
            author = col2.text_input("Autor", placeholder="Nome do autor ou autora")
            col3, col4 = st.columns(2)
            month = col3.selectbox("Mês do endomarketing", [""] + month_options())
            year = col4.number_input("Ano", min_value=2020, max_value=2100, value=date.today().year, step=1)
            notes = st.text_area("Observações", placeholder="Opcional: edição, localização ou estado do exemplar.")
            submitted = st.form_submit_button("Adicionar ao acervo", type="primary", width="stretch")

        if submitted:
            if not title.strip():
                st.error("Informe o título do livro.")
            else:
                run_command(
                    """
                    INSERT INTO books (title, author, month_label, year, notes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (title.strip(), author.strip(), month or None, year, notes.strip()),
                )
                st.success("Livro cadastrado.")
                st.rerun()

    if not rows:
        render_empty_state(
            "O acervo ainda está vazio",
            "Use a seção acima para cadastrar o primeiro livro da Biblioteca HCI.",
        )
        return

    filter_col1, filter_col2 = st.columns([1.4, .6])
    search = filter_col1.text_input(
        "Buscar no acervo",
        placeholder="Título, autor, mês ou nome do assessor",
    )
    status_filter = filter_col2.selectbox("Situação", ["Todos", "Disponíveis", "Emprestados"])
    filtered = []
    for row in rows:
        haystack = " ".join(str(row[key] or "") for key in ["title", "author", "month_label", "year", "status", "borrower"])
        matches_search = search.lower() in haystack.lower()
        matches_status = (
            status_filter == "Todos"
            or (status_filter == "Disponíveis" and row["status"] == "Disponível")
            or (status_filter == "Emprestados" and row["status"] == "Emprestado")
        )
        if matches_search and matches_status:
            filtered.append(row)

    st.markdown(
        f"""
        <div class="summary-line">
            <span>Livros que correspondem aos filtros</span>
            <span class="summary-pill">{len(filtered)} de {len(rows)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    table = [
        {
            "Título": row["title"],
            "Autor": row["author"] or "",
            "Mês": row["month_label"] or "",
            "Ano": row["year"] or "",
            "Status": row["status"],
            "Com": row["borrower"] or "",
            "Desde": parse_iso(row["checkout_date"]).strftime("%d/%m/%Y") if row["checkout_date"] else "",
            "Dias": days_between(row["checkout_date"]) if row["checkout_date"] else "",
            "Observações": row["notes"] or "",
        }
        for row in filtered
    ]
    if table:
        st.dataframe(table, width="stretch", hide_index=True)
    else:
        render_empty_state("Nenhum livro encontrado", "Tente outro termo ou altere o filtro de situação.")


def render_history() -> None:
    section_title("Consulta de movimentações")
    rows = loan_history()
    if not rows:
        render_empty_state(
            "Ainda não há movimentações",
            "Os empréstimos e as devoluções aparecerão aqui automaticamente.",
        )
        return

    filter_col1, filter_col2 = st.columns([1.4, .6])
    search = filter_col1.text_input(
        "Buscar no histórico",
        placeholder="Livro, autor ou nome do assessor",
    )
    status_filter = filter_col2.selectbox("Situação", ["Todas", "Em aberto", "Devolvidos"])

    filtered = []
    for row in rows:
        haystack = " ".join(
            str(row[key] or "")
            for key in ["title", "author", "name", "checkout_date", "return_date", "notes"]
        )
        matches_search = search.lower() in haystack.lower()
        matches_status = (
            status_filter == "Todas"
            or (status_filter == "Em aberto" and not row["return_date"])
            or (status_filter == "Devolvidos" and bool(row["return_date"]))
        )
        if matches_search and matches_status:
            filtered.append(row)

    table = [
        {
            "Livro": row["title"],
            "Autor": row["author"] or "",
            "Assessor": row["name"],
            "Retirada": parse_iso(row["checkout_date"]).strftime("%d/%m/%Y"),
            "Devolução": parse_iso(row["return_date"]).strftime("%d/%m/%Y") if row["return_date"] else "Em aberto",
            "Dias": days_between(row["checkout_date"], row["return_date"]),
            "Observações": row["notes"] or "",
        }
        for row in filtered
    ]
    st.markdown(
        f"""
        <div class="summary-line">
            <span>Movimentações que correspondem aos filtros</span>
            <span class="summary-pill">{len(table)} de {len(rows)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if table:
        st.dataframe(table, width="stretch", hide_index=True)
        st.download_button(
            "Baixar histórico exibido (.csv)",
            data=to_csv(table),
            file_name=f"historico_biblioteca_hci_{today_iso()}.csv",
            mime="text/csv",
        )
    else:
        render_empty_state("Nenhuma movimentação encontrada", "Tente outro termo ou altere o filtro de situação.")


def render_sidebar() -> str:
    cloud_database = is_cloud_database()
    st.sidebar.markdown(
        f"""
        <div class="sidebar-brand">
            {brand_mark("sidebar-mark", "#ffffff")}
            <div class="sidebar-sub">advisors</div>
            <div class="sidebar-title">Biblioteca HCI</div>
            <div class="sidebar-tagline">Controle de empréstimos</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio(
        "Navegação principal",
        PAGES,
        label_visibility="collapsed",
        key="navigation",
    )

    st.sidebar.markdown(
        f"""
        <div class="sidebar-status">
            <span class="sidebar-status-dot"></span>
            <span>{'Uso compartilhado' if cloud_database else 'Uso local'}<br>
            {'Dados sincronizados em nuvem' if cloud_database else 'Dados salvos neste computador'}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.divider()
    if not cloud_database and DB_PATH.exists():
        st.sidebar.download_button(
            "Backup do banco (.db)",
            data=DB_PATH.read_bytes(),
            file_name=f"biblioteca_hci_{today_iso()}.db",
            mime="application/octet-stream",
            width="stretch",
        )
        st.sidebar.caption("Guarde uma cópia periódica em uma pasta segura da empresa.")
    return page


def get_setting(key: str, default: str | None = None) -> str | None:
    """Lê uma configuração de variável de ambiente ou dos secrets do Streamlit."""
    value = os.environ.get(key)
    if value is not None:
        return value
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


def is_cloud_database() -> bool:
    return bool(get_setting("TURSO_DATABASE_URL") and get_setting("TURSO_AUTH_TOKEN"))


def require_password() -> None:
    """Acesso por senha única (compartilhada). Só é exigida quando BIBLIOTECA_SENHA
    está definida (variável de ambiente ou secret); no uso local o app abre direto."""
    expected = get_setting("BIBLIOTECA_SENHA")
    if not expected or st.session_state.get("auth_ok"):
        return

    render_header(PAGE_DASHBOARD)
    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        st.markdown("#### Acesso restrito")
        password = st.text_input(
            "Senha",
            type="password",
            label_visibility="collapsed",
            placeholder="Senha de acesso",
        )
        if st.button("Entrar", type="primary", width="stretch"):
            if hmac.compare_digest(password, expected):
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()


def main() -> None:
    init_db()
    inject_styles()
    require_password()

    page = render_sidebar()
    render_header(page)
    if page == PAGE_DASHBOARD:
        render_dashboard()
    elif page == PAGE_NEW_LOAN:
        render_new_loan()
    elif page == PAGE_RETURN:
        render_returns()
    elif page == PAGE_BOOKS:
        render_books()
    else:
        render_history()


if __name__ == "__main__":
    main()
