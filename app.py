from __future__ import annotations

import csv
import hmac
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


st.set_page_config(
    page_title="Biblioteca HCI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


@contextmanager
def connect_db():
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
            """
        )


def run_query(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    with connect_db() as conn:
        return conn.execute(query, params).fetchall()


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
            collaborators.name,
            collaborators.department,
            collaborators.email
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
            collaborators.name,
            collaborators.department
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
            return int(existing["id"])

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
                --hci-blue-700: #223554;
                --hci-gold: #e0ad55;
                --hci-gold-soft: rgba(224, 173, 85, .16);
                --hci-slate: #5f657f;
                --hci-gray: #dbdbdb;
                --hci-white: #ffffff;
                --hci-ink: #182845;
                --line: rgba(24, 40, 69, .12);
                --line-strong: rgba(24, 40, 69, .22);
                --shadow-sm: 0 1px 2px rgba(24, 40, 69, .06);
                --shadow-md: 0 12px 30px rgba(24, 40, 69, .08);
                --radius: 10px;
                --radius-sm: 8px;
            }

            html, body, [class*="css"],
            button, input, textarea, select {
                font-family: "Red Hat Display", sans-serif;
            }

            .stApp {
                color: var(--hci-ink);
                background:
                    radial-gradient(circle at 88% 2%, rgba(224, 173, 85, .10), transparent 22rem),
                    linear-gradient(180deg, #ffffff 0%, #f7f8fa 60%, #f3f4f7 100%);
            }

            h1, h2, h3 {
                font-family: "Red Hat Display", sans-serif;
                letter-spacing: 0;
                color: var(--hci-blue);
                font-weight: 500;
            }

            /* ---- Barra lateral: azul HCI com o elemento gráfico em dourado ---- */
            [data-testid="stSidebar"] {
                background:
                    __PATTERN_SIDEBAR__ 0 0 / 132px 132px,
                    linear-gradient(180deg, #182845 0%, #16243f 100%);
                border-right: 1px solid rgba(224, 173, 85, .28);
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
                gap: .12rem;
            }

            [data-testid="stSidebar"] [role="radiogroup"] label {
                border-radius: var(--radius-sm);
                padding: .4rem .6rem;
                margin: 0;
                transition: background .15s ease, box-shadow .15s ease;
            }

            [data-testid="stSidebar"] [role="radiogroup"] label:hover {
                background: rgba(255, 255, 255, .08);
            }

            [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
                background: var(--hci-gold-soft);
                box-shadow: inset 3px 0 0 var(--hci-gold);
            }

            /* ---- Cabeçalho da barra lateral ---- */
            .sidebar-brand {
                padding: .1rem .15rem 1rem;
                margin-bottom: .9rem;
                border-bottom: 1px solid rgba(224, 173, 85, .28);
            }

            .sidebar-mark {
                display: block;
                height: 1.55rem;
                width: auto;
            }

            .sidebar-sub {
                margin: .26rem 0 0 .12rem;
                color: rgba(255, 255, 255, .8);
                font-size: .58rem;
                font-weight: 400;
                letter-spacing: .34rem;
            }

            .sidebar-title {
                position: relative;
                margin-top: .95rem;
                padding-bottom: .5rem;
                color: #ffffff;
                font-size: 1.18rem;
                font-weight: 600;
            }

            .sidebar-title::after {
                content: "";
                position: absolute;
                left: 0;
                bottom: 0;
                width: 2.2rem;
                height: 2px;
                background: var(--hci-gold);
            }

            .sidebar-tagline {
                margin-top: .55rem;
                color: rgba(255, 255, 255, .62);
                font-size: .8rem;
            }

            /* ---- Métricas ---- */
            [data-testid="stMetric"] {
                position: relative;
                overflow: hidden;
                background: #ffffff;
                border: 1px solid var(--line);
                border-radius: var(--radius);
                padding: 1rem 1.1rem;
                box-shadow: var(--shadow-md);
            }

            [data-testid="stMetric"]::before {
                content: "";
                position: absolute;
                left: 0;
                top: 0;
                bottom: 0;
                width: 3px;
                background: var(--hci-gold);
            }

            [data-testid="stMetric"] [data-testid="stMetricLabel"] {
                color: var(--hci-slate);
            }

            [data-testid="stMetric"] [data-testid="stMetricValue"] {
                color: var(--hci-blue);
                font-weight: 600;
            }

            /* ---- Hero da marca ---- */
            .library-hero {
                position: relative;
                overflow: hidden;
                border: 1px solid var(--line);
                border-radius: var(--radius);
                padding: 1.5rem 1.7rem 1.6rem;
                margin-bottom: 1.2rem;
                background:
                    radial-gradient(circle at 96% 10%, rgba(224, 173, 85, .14), transparent 24rem),
                    linear-gradient(135deg, #ffffff 0%, #f7f8fa 58%, #eef0f4 100%);
                color: var(--hci-blue);
                box-shadow: var(--shadow-md);
            }

            .library-hero::before {
                content: "";
                position: absolute;
                inset: 0;
                pointer-events: none;
                background: __PATTERN_HERO__ 0 0 / 120px 120px;
                -webkit-mask-image: linear-gradient(90deg, transparent 52%, #000 102%);
                mask-image: linear-gradient(90deg, transparent 52%, #000 102%);
            }

            .brand-lockup {
                position: relative;
                z-index: 1;
                display: inline-flex;
                flex-direction: column;
                line-height: .9;
                margin-bottom: .85rem;
            }

            .brand-mark {
                display: block;
                height: 2.7rem;
                width: auto;
            }

            .brand-sub {
                margin-left: .28rem;
                margin-top: .34rem;
                color: var(--hci-slate);
                font-size: .7rem;
                font-weight: 400;
                letter-spacing: .4rem;
            }

            .library-hero h1 {
                position: relative;
                z-index: 1;
                color: var(--hci-blue);
                font-size: clamp(1.9rem, 3.6vw, 2.9rem);
                font-weight: 500;
                margin: 0;
            }

            .library-hero h1::after {
                content: "";
                display: block;
                width: 4.6rem;
                height: 2px;
                margin-top: .7rem;
                background: var(--hci-gold);
            }

            .library-hero p {
                position: relative;
                z-index: 1;
                max-width: 760px;
                margin: .8rem 0 0;
                font-size: 1.02rem;
                color: var(--hci-slate);
                font-weight: 400;
            }

            /* ---- Título de seção: assinatura do Brandbook (traço dourado) ---- */
            .hci-section {
                margin: 1.5rem 0 .9rem;
            }

            .hci-section h2 {
                position: relative;
                margin: 0;
                padding-bottom: .5rem;
                font-size: 1.3rem;
                font-weight: 500;
                color: var(--hci-blue);
            }

            .hci-section h2::after {
                content: "";
                position: absolute;
                left: 0;
                bottom: 0;
                width: 2.6rem;
                height: 2px;
                background: var(--hci-gold);
            }

            /* ---- Tabelas, botões, campos ---- */
            div[data-testid="stDataFrame"] {
                border: 1px solid var(--line);
                border-radius: var(--radius-sm);
                overflow: hidden;
            }

            .stButton > button,
            .stDownloadButton > button,
            .stFormSubmitButton > button {
                border-radius: var(--radius-sm);
                border: 1px solid var(--line-strong);
                font-weight: 600;
                color: var(--hci-blue);
                background: #ffffff;
                transition: border-color .15s ease, background .15s ease, color .15s ease;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover,
            .stFormSubmitButton > button:hover {
                border-color: var(--hci-gold);
                color: var(--hci-blue);
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
                background: var(--hci-blue-700);
                border-color: var(--hci-gold);
                color: #ffffff;
            }

            .stTextInput input,
            .stTextArea textarea,
            .stNumberInput input,
            .stDateInput input,
            .stSelectbox div[data-baseweb="select"] > div {
                border-radius: var(--radius-sm);
            }

            .stAlert {
                border-radius: var(--radius-sm);
            }

            [data-testid="stExpander"] {
                border: 1px solid var(--line);
                border-radius: var(--radius-sm);
            }
        </style>
    """
    css = css.replace("__PATTERN_SIDEBAR__", _brand_pattern("0.16"))
    css = css.replace("__PATTERN_HERO__", _brand_pattern("0.5"))
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


def render_header() -> None:
    st.markdown(
        f"""
        <div class="library-hero">
            <div class="brand-lockup" aria-label="HCI Advisors">
                {brand_mark("brand-mark", "#182845")}
                <span class="brand-sub">advisors</span>
            </div>
            <h1>Biblioteca HCI</h1>
            <p>Controle simples dos livros do endomarketing: quem pegou, quando pegou,
            há quantos dias está emprestado e quando voltou para a estante.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard() -> None:
    books = active_books()
    loans = active_loans()
    open_days = [days_between(row["checkout_date"]) for row in loans]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Livros cadastrados", len(books))
    col2.metric("Disponíveis", len([book for book in books if book["status"] == "Disponível"]))
    col3.metric("Emprestados", len(loans))
    col4.metric("Maior empréstimo", f"{max(open_days) if open_days else 0} dias")

    section_title("Empréstimos em aberto")
    if not loans:
        st.info("Nenhum livro emprestado no momento.")
        return

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
    st.dataframe(table, use_container_width=True, hide_index=True)


def render_new_loan() -> None:
    section_title("Registrar empréstimo")
    books = available_books()

    if not books:
        st.warning("Não há livros disponíveis para empréstimo.")
        return

    book_options = {f"{row['title']} — {row['author'] or 'Autor não informado'}": row["id"] for row in books}

    with st.form("new_loan_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([1.2, 1.2, .8])
        book_label = col1.selectbox("Livro", list(book_options.keys()))
        collaborator_name = col2.text_input("Nome completo do colaborador *")
        checkout = col3.date_input("Data de retirada", value=date.today(), format="DD/MM/YYYY")
        notes = st.text_area("Observações", placeholder="Opcional: estado do livro, combinado com o colaborador etc.")
        submitted = st.form_submit_button("Salvar empréstimo", type="primary")

    if submitted:
        if not collaborator_name.strip():
            st.error("Informe o nome completo do colaborador.")
            return

        collaborator_id = get_or_create_collaborator(collaborator_name)
        run_command(
            """
            INSERT INTO loans (book_id, collaborator_id, checkout_date, notes)
            VALUES (?, ?, ?, ?)
            """,
            (book_options[book_label], collaborator_id, checkout.isoformat(), notes.strip()),
        )
        st.success("Empréstimo registrado.")
        st.rerun()


def render_returns() -> None:
    section_title("Registrar devolução")
    loans = active_loans()
    if not loans:
        st.info("Não há devoluções pendentes.")
        return

    loan_options = {
        f"{row['title']} com {row['name']} desde {parse_iso(row['checkout_date']).strftime('%d/%m/%Y')} ({days_between(row['checkout_date'])} dias)": row[
            "id"
        ]
        for row in loans
    }

    with st.form("return_form"):
        loan_label = st.selectbox("Empréstimo em aberto", list(loan_options.keys()))
        returned = st.date_input("Data de devolução", value=date.today(), format="DD/MM/YYYY")
        submitted = st.form_submit_button("Confirmar devolução", type="primary")

    if submitted:
        run_command(
            """
            UPDATE loans
            SET return_date = ?
            WHERE id = ?
              AND return_date IS NULL
            """,
            (returned.isoformat(), loan_options[loan_label]),
        )
        st.success("Devolução registrada.")
        st.rerun()


def render_books() -> None:
    section_title("Livros")

    with st.expander("Cadastrar novo livro", expanded=True):
        with st.form("book_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            title = col1.text_input("Título *")
            author = col2.text_input("Autor")
            col3, col4 = st.columns(2)
            month = col3.selectbox("Mês do endomarketing", [""] + month_options())
            year = col4.number_input("Ano", min_value=2020, max_value=2100, value=date.today().year, step=1)
            notes = st.text_area("Observações")
            submitted = st.form_submit_button("Cadastrar livro", type="primary")

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

    rows = active_books()
    if not rows:
        st.info("Ainda não há livros cadastrados.")
        return

    search = st.text_input("Buscar livro", placeholder="Digite título, autor ou mês")
    filtered = []
    for row in rows:
        haystack = " ".join(str(row[key] or "") for key in ["title", "author", "month_label", "year", "status", "borrower"])
        if search.lower() in haystack.lower():
            filtered.append(row)

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
    st.dataframe(table, use_container_width=True, hide_index=True)


def render_history() -> None:
    section_title("Histórico")
    rows = loan_history()
    if not rows:
        st.info("Ainda não há movimentações.")
        return

    table = [
        {
            "Livro": row["title"],
            "Autor": row["author"] or "",
            "Colaborador": row["name"],
            "Retirada": parse_iso(row["checkout_date"]).strftime("%d/%m/%Y"),
            "Devolução": parse_iso(row["return_date"]).strftime("%d/%m/%Y") if row["return_date"] else "Em aberto",
            "Dias": days_between(row["checkout_date"], row["return_date"]),
            "Observações": row["notes"] or "",
        }
        for row in rows
    ]
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.download_button(
        "Baixar histórico em CSV",
        data=to_csv(table),
        file_name=f"historico_biblioteca_hci_{today_iso()}.csv",
        mime="text/csv",
    )


def render_sidebar() -> str:
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
        "Navegação",
        ["Painel", "Novo empréstimo", "Devolução", "Livros", "Histórico"],
    )

    st.sidebar.divider()
    if DB_PATH.exists():
        st.sidebar.download_button(
            "Backup do banco (.db)",
            data=DB_PATH.read_bytes(),
            file_name=f"biblioteca_hci_{today_iso()}.db",
            mime="application/octet-stream",
            use_container_width=True,
        )
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


def require_password() -> None:
    """Acesso por senha única (compartilhada). Só é exigida quando BIBLIOTECA_SENHA
    está definida (variável de ambiente ou secret); no uso local o app abre direto."""
    expected = get_setting("BIBLIOTECA_SENHA")
    if not expected or st.session_state.get("auth_ok"):
        return

    render_header()
    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        st.markdown("#### Acesso restrito")
        password = st.text_input(
            "Senha",
            type="password",
            label_visibility="collapsed",
            placeholder="Senha de acesso",
        )
        if st.button("Entrar", type="primary", use_container_width=True):
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
    render_header()

    page = render_sidebar()
    if page == "Painel":
        render_dashboard()
    elif page == "Novo empréstimo":
        render_new_loan()
    elif page == "Devolução":
        render_returns()
    elif page == "Livros":
        render_books()
    else:
        render_history()


if __name__ == "__main__":
    main()
