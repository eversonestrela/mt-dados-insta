"""Caminhos, banco de dados (SQLite), criptografia e configurações."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
MIDIA = DADOS / "midia"
CACHE = DADOS / "cache"
FOTOS = DADOS / "fotos"
FONTES = RAIZ / "fontes"
ARQ_DB = DADOS / "app.db"
ARQ_CHAVE = DADOS / ".chave"
ARQ_AGENDA = DADOS / "agenda.csv"

for _p in (DADOS, MIDIA, CACHE, FOTOS):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- configurações padrão
PADRAO: dict = {
    "fuso": "America/Cuiaba",
    # IA (Claude)
    "ia_ativa": False,
    # "claude_code": usa o comando `claude` logado na assinatura (Pro/Max) - sem cobrança extra
    # "api": usa chave da API (cobrança por token no Console)
    "ia_provedor": "claude_code",
    "claude_caminho": "",           # vazio = procura o comando `claude` no PATH
    "ia_modelo": "haiku",           # haiku | sonnet | opus (ou nome completo do modelo)
    "ia_limite_diario": 20000,      # tokens (entrada + saída) por dia
    "ia_limite_mensal": 400000,     # tokens (entrada + saída) por mês
    "ia_max_saida": 450,            # teto de tokens de resposta por chamada
    # geração
    "geracao_horario": "05:00",
    "posts_por_dia": 5,
    # hospedagem das mídias
    "hospedagem": "cloudinary",     # cloudinary | url_publica
    "cloudinary_cloud": "",
    "cloudinary_key": "",
    "url_publica_base": "",
    # fontes de dados
    "satelite_referencia": "AQUA_M-T",
    "clima_cidades": "Cuiabá;-15.601;-56.097",
    "diario_termos": "licitação;nomeação;decreto;obra",
}
# configurações guardadas criptografadas
SECRETAS = {"anthropic_chave", "cloudinary_segredo"}

_lock = threading.RLock()


def agora() -> datetime:
    return datetime.now(ZoneInfo(cfg("fuso")))


# ---------------------------------------------------------------- criptografia
def _fernet() -> Fernet:
    if not ARQ_CHAVE.exists():
        ARQ_CHAVE.write_bytes(Fernet.generate_key())
    return Fernet(ARQ_CHAVE.read_bytes())


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode() if texto else ""


def decifrar(texto: str) -> str:
    if not texto:
        return ""
    try:
        return _fernet().decrypt(texto.encode()).decode()
    except InvalidToken:
        return ""


# ---------------------------------------------------------------- banco
ESQUEMA = """
CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    arroba TEXT DEFAULT '',
    ig_user_id TEXT DEFAULT '',
    api_host TEXT DEFAULT 'graph.instagram.com',
    api_versao TEXT DEFAULT 'v26.0',
    token_cifrado TEXT DEFAULT '',
    token_expira_em TEXT DEFAULT '',
    token_atualizado_em TEXT DEFAULT '',
    ativa INTEGER DEFAULT 1,
    auto_aprovar INTEGER DEFAULT 0,
    horarios TEXT DEFAULT '["07:30","11:30","13:00","18:00","20:30"]',
    pautas TEXT DEFAULT '["queimadas","clima","municipio","municipio_reel","ranking","diario","agenda"]',
    municipios_foco TEXT DEFAULT '',
    cor_destaque TEXT DEFAULT '#B4441C',
    criada_em TEXT
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_id INTEGER NOT NULL,
    dia TEXT NOT NULL,
    tipo TEXT NOT NULL,          -- feed | carrossel | story | reel
    pauta TEXT NOT NULL,
    titulo TEXT,
    legenda TEXT DEFAULT '',
    midias TEXT DEFAULT '[]',
    fonte TEXT DEFAULT '',
    dados TEXT DEFAULT '{}',
    avisos TEXT DEFAULT '[]',
    texto_por TEXT DEFAULT 'modelo',
    revisao_obrigatoria INTEGER DEFAULT 0,
    status TEXT DEFAULT 'revisao', -- revisao | aprovado | publicando | publicado | rejeitado | erro
    agendado_para TEXT,
    publicado_em TEXT,
    ig_media_id TEXT,
    link TEXT,
    erro TEXT,
    criado_em TEXT,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS uso_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    momento TEXT, dia TEXT, mes TEXT,
    modelo TEXT, entrada INTEGER, saida INTEGER,
    finalidade TEXT, post_id INTEGER
);
CREATE TABLE IF NOT EXISTS serie_queimadas (
    dia TEXT PRIMARY KEY, total INTEGER, satelite TEXT
);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, momento TEXT, nivel TEXT, msg TEXT
);
"""


def _conectar() -> sqlite3.Connection:
    con = sqlite3.connect(ARQ_DB, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def db():
    with _lock:
        con = _conectar()
        try:
            yield con
            con.commit()
        finally:
            con.close()


def iniciar_db() -> None:
    with db() as c:
        c.executescript(ESQUEMA)


# ---------------------------------------------------------------- config
def cfg(chave: str):
    with db() as c:
        r = c.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
    if r is None:
        return PADRAO.get(chave, "")
    valor = json.loads(r["valor"])
    if chave in SECRETAS:
        return decifrar(valor)
    return valor


def salvar_cfg(chave: str, valor) -> None:
    if chave in SECRETAS:
        valor = cifrar(valor)
    with db() as c:
        c.execute(
            "INSERT INTO config(chave, valor) VALUES(?,?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, json.dumps(valor, ensure_ascii=False)),
        )


def log(msg: str, nivel: str = "info") -> None:
    print(f"[{nivel}] {msg}")
    try:
        with db() as c:
            c.execute(
                "INSERT INTO log(momento, nivel, msg) VALUES(?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), nivel, msg[:2000]),
            )
    except Exception:  # noqa: BLE001 - log nunca pode derrubar o app
        pass


# ---------------------------------------------------------------- contas
def contas(somente_ativas: bool = False) -> list[dict]:
    sql = "SELECT * FROM contas" + (" WHERE ativa=1" if somente_ativas else "") + " ORDER BY id"
    with db() as c:
        return [dict(r) for r in c.execute(sql)]


def conta(conta_id: int) -> dict | None:
    with db() as c:
        r = c.execute("SELECT * FROM contas WHERE id=?", (conta_id,)).fetchone()
    return dict(r) if r else None


def token_da_conta(ct: dict) -> str:
    return decifrar(ct.get("token_cifrado") or "")


# ---------------------------------------------------------------- posts
def post(post_id: int) -> dict | None:
    with db() as c:
        r = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not r:
        return None
    p = dict(r)
    for k in ("midias", "dados", "avisos"):
        p[k] = json.loads(p[k] or ("[]" if k != "dados" else "{}"))
    return p


def atualizar_post(post_id: int, **campos) -> None:
    for k in ("midias", "dados", "avisos"):
        if k in campos and not isinstance(campos[k], str):
            campos[k] = json.dumps(campos[k], ensure_ascii=False)
    campos["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    sets = ", ".join(f"{k}=?" for k in campos)
    with db() as c:
        c.execute(f"UPDATE posts SET {sets} WHERE id=?", (*campos.values(), post_id))
