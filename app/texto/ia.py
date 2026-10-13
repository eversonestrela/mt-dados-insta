"""Acesso ao Claude com teto rígido de tokens.

Dois provedores:
- "claude_code" (padrão): chama o comando `claude -p` (Claude Code) logado na sua
  assinatura Pro/Max. Antes de cada chamada o app confere, com `claude auth status`,
  que o login é da assinatura. Se estiver usando chave de API (que gera cobrança),
  a chamada é bloqueada. As variáveis ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN são
  removidas do ambiente do processo para não haver cobrança por engano.
- "api": usa a API com chave própria (cobrada por token no Console).

Orçamento: antes de chamar, o app reserva a estimativa (entrada + teto de saída) e
recusa se ela passar do limite diário ou mensal. Depois grava o uso real.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import time

from ..base import DADOS, agora, cfg, db, log

_trava = threading.Lock()
_reservado = 0
_auth_cache: tuple[float, dict] | None = None

ALIASES_API = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
VARS_PROIBIDAS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                  "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_BASE_URL")
LOGINS_ASSINATURA = {"claude.ai", "oauth_token"}


class IAIndisponivel(Exception):
    """IA desligada, sem orçamento, sem login ou com erro. O chamador usa o texto-modelo."""


# ------------------------------------------------------------------ orçamento
def uso() -> dict:
    hoje = agora()
    with db() as c:
        dia = c.execute("SELECT COALESCE(SUM(entrada+saida),0) t, COUNT(*) n FROM uso_ia WHERE dia=?",
                        (hoje.date().isoformat(),)).fetchone()
        mes = c.execute("SELECT COALESCE(SUM(entrada+saida),0) t FROM uso_ia WHERE mes=?",
                        (hoje.strftime("%Y-%m"),)).fetchone()
    lim_d, lim_m = int(cfg("ia_limite_diario")), int(cfg("ia_limite_mensal"))
    return {
        "dia": dia["t"], "chamadas_dia": dia["n"], "mes": mes["t"],
        "limite_dia": lim_d, "limite_mes": lim_m,
        "resta_dia": max(0, lim_d - dia["t"]), "resta_mes": max(0, lim_m - mes["t"]),
    }


def _reservar(estimativa: int) -> None:
    global _reservado
    u = uso()
    if u["dia"] + _reservado + estimativa > u["limite_dia"]:
        raise IAIndisponivel(f"Limite diário de tokens atingido ({u['dia']}/{u['limite_dia']})")
    if u["mes"] + _reservado + estimativa > u["limite_mes"]:
        raise IAIndisponivel(f"Limite mensal de tokens atingido ({u['mes']}/{u['limite_mes']})")
    _reservado += estimativa


def _liberar(estimativa: int) -> None:
    global _reservado
    _reservado = max(0, _reservado - estimativa)


def _registrar(modelo: str, entrada: int, saida: int, finalidade: str, post_id: int | None) -> None:
    m = agora()
    with db() as c:
        c.execute(
            "INSERT INTO uso_ia(momento,dia,mes,modelo,entrada,saida,finalidade,post_id) VALUES(?,?,?,?,?,?,?,?)",
            (m.isoformat(timespec="seconds"), m.date().isoformat(), m.strftime("%Y-%m"),
             modelo, int(entrada), int(saida), finalidade, post_id),
        )


# ------------------------------------------------------------------ Claude Code (assinatura)
def _ambiente_limpo() -> dict:
    env = dict(os.environ)
    for v in VARS_PROIBIDAS:
        env.pop(v, None)
    return env


def caminho_claude() -> str | None:
    p = (cfg("claude_caminho") or "").strip()
    if p:
        return p if os.path.exists(p) else None
    achado = shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe")
    if achado:
        return achado
    # local padrão do instalador oficial (Windows e Mac/Linux)
    for p in (os.path.expanduser(r"~\.local\bin\claude.exe"), os.path.expanduser("~/.local/bin/claude")):
        if os.path.exists(p):
            return p
    return None


def status_login(forcar: bool = False) -> dict:
    """{'ok': bool, 'metodo': str, 'msg': str}"""
    global _auth_cache
    if _auth_cache and not forcar and time.time() - _auth_cache[0] < 600:
        return _auth_cache[1]
    exe = caminho_claude()
    if not exe:
        res = {"ok": False, "metodo": "none",
               "msg": "Comando `claude` não encontrado. Instale o Claude Code e rode `claude` uma vez para fazer login."}
    else:
        try:
            p = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60, env=_ambiente_limpo())
            j = json.loads(p.stdout or "{}")
            metodo = j.get("authMethod", "none")
            if metodo in LOGINS_ASSINATURA:
                res = {"ok": True, "metodo": metodo, "msg": "Logado na assinatura Claude (sem cobrança por token)."}
            elif metodo == "none":
                res = {"ok": False, "metodo": metodo, "msg": "Claude Code não está logado. Abra o PowerShell e rode: claude"}
            else:
                res = {"ok": False, "metodo": metodo,
                       "msg": f"O Claude Code está usando '{metodo}', que é cobrado por token. "
                              "Bloqueado. Rode `claude auth logout` e depois `claude` para entrar com a conta Pro."}
        except json.JSONDecodeError:
            res = {"ok": False, "metodo": "?", "msg": "Não consegui ler `claude auth status`. Atualize com: claude update"}
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "metodo": "?", "msg": f"Erro ao checar login do Claude Code: {e}"}
    _auth_cache = (time.time(), res)
    return res


def _chamar_claude_code(sistema: str, usuario: str, max_saida: int) -> tuple[str, int, int, str]:
    login = status_login()
    if not login["ok"]:
        raise IAIndisponivel(login["msg"])
    exe = caminho_claude()
    modelo = str(cfg("ia_modelo") or "haiku")
    pasta = DADOS / "claude_vazio"  # pasta vazia: o Claude não lê nada do seu computador
    pasta.mkdir(exist_ok=True)
    arq_sistema = pasta / "sistema.txt"
    arq_sistema.write_text(sistema + f"\n\nResponda em no máximo {max_saida} tokens.", encoding="utf-8")

    base = [exe, "-p", "--output-format", "json", "--model", modelo,
            "--system-prompt-file", str(arq_sistema), "--max-turns", "1"]
    opcionais = ["--tools", "", "--no-session-persistence", "--strict-mcp-config"]
    for cmd in (base + opcionais, base):
        p = subprocess.run(cmd, input=usuario, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=240, cwd=pasta, env=_ambiente_limpo())
        erro_flag = "unknown option" in (p.stderr or "").lower() or "unknown argument" in (p.stderr or "").lower()
        if not erro_flag:
            break
    try:
        j = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise IAIndisponivel(f"Resposta inesperada do Claude Code: {(p.stderr or p.stdout)[:300]}") from e
    u = j.get("usage") or {}
    entrada = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    saida = int(u.get("output_tokens") or 0)
    if j.get("is_error"):
        raise IAIndisponivel(f"Claude Code retornou erro: {str(j.get('result'))[:300]}")
    return str(j.get("result") or ""), entrada, saida, modelo


# ------------------------------------------------------------------ API (cobrada)
def _chamar_api(sistema: str, usuario: str, max_saida: int, estimar_apenas: bool = False):
    chave = cfg("anthropic_chave")
    if not chave:
        raise IAIndisponivel("Chave da API não configurada")
    import anthropic

    cliente = anthropic.Anthropic(api_key=chave)
    modelo = ALIASES_API.get(str(cfg("ia_modelo")), str(cfg("ia_modelo")))
    msgs = [{"role": "user", "content": usuario}]
    if estimar_apenas:
        return cliente.messages.count_tokens(model=modelo, system=sistema, messages=msgs).input_tokens
    r = cliente.messages.create(model=modelo, system=sistema, messages=msgs, max_tokens=max_saida)
    texto = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    u = r.usage
    entrada = (u.input_tokens or 0) + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
    return texto, entrada, u.output_tokens or 0, modelo


# ------------------------------------------------------------------ ponto de entrada
def gerar(sistema: str, usuario: str, finalidade: str, post_id: int | None = None) -> str:
    if not cfg("ia_ativa"):
        raise IAIndisponivel("IA desligada nas configurações")
    provedor = cfg("ia_provedor")
    max_saida = int(cfg("ia_max_saida"))

    if provedor == "api":
        try:
            entrada_est = _chamar_api(sistema, usuario, max_saida, estimar_apenas=True)
        except IAIndisponivel:
            raise
        except Exception:  # noqa: BLE001 - se a contagem falhar, estima por caracteres
            entrada_est = math.ceil((len(sistema) + len(usuario)) / 2.5)
    else:
        # Claude Code acrescenta algumas instruções próprias; margem de 50%.
        entrada_est = math.ceil((len(sistema) + len(usuario)) / 2.5 * 1.5) + 300
    estimativa = entrada_est + max_saida

    with _trava:
        _reservar(estimativa)
    try:
        if provedor == "api":
            texto, entrada, saida, modelo = _chamar_api(sistema, usuario, max_saida)
        else:
            texto, entrada, saida, modelo = _chamar_claude_code(sistema, usuario, max_saida)
    except IAIndisponivel:
        raise
    except Exception as e:  # noqa: BLE001
        raise IAIndisponivel(f"Falha ao chamar o Claude: {e}") from e
    finally:
        with _trava:
            _liberar(estimativa)
    _registrar(modelo, entrada, saida, finalidade, post_id)
    log(f"Claude ({provedor}/{modelo}) {finalidade}: {entrada}+{saida} tokens")
    return texto.strip()
