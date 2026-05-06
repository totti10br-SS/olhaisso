"""
Gerador de link de afiliado Mercado Livre
Usa o endpoint oficial: /affiliate-program/api/v2/stripe/user/links
Autenticado via cookies de sessão do portal de afiliados
"""

import os
import sys
import json
import requests

ML_TAG = os.getenv("ML_PUBLISHER_ID", "ot20260326074822")

# Cookies extraídos do browser (sessão autenticada)
# Renovar quando expirar: exportar novamente com Cookie-Editor e atualizar ML_COOKIES
ML_COOKIES_JSON = os.getenv("ML_COOKIES_JSON", "")

def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()


def _carregar_cookies():
    """Converte o JSON de cookies do Cookie-Editor para dict simples."""
    if not ML_COOKIES_JSON:
        return {}
    try:
        lista = json.loads(ML_COOKIES_JSON)
        return {c["name"]: c["value"] for c in lista if "name" in c and "value" in c}
    except Exception as e:
        log(f"ML Link: erro ao carregar cookies: {e}")
        return {}


def gerar_link_afiliado_ml(url_produto, item_id=""):
    """
    Gera link meli.la via endpoint oficial do ML.
    Retorna short_url (meli.la/xxx) ou None se falhar.
    """
    cookies = _carregar_cookies()
    if not cookies:
        log("ML Link: ML_COOKIES_JSON não configurado")
        return None

    # Pega o x-csrf-token dos cookies
    csrf = cookies.get("_csrf", "")

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://www.mercadolivre.com.br",
        "referer": url_produto,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "x-csrf-token": csrf,
    }

    payload = {
        "tag": ML_TAG,
        "url": url_produto,
    }
    if item_id:
        payload["buy_box_winner"] = item_id

    try:
        r = requests.post(
            "https://www.mercadolivre.com.br/affiliate-program/api/v2/stripe/user/links",
            json=payload,
            headers=headers,
            cookies=cookies,
            timeout=15,
        )
        log(f"ML Link: status {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            short_url = data.get("short_url", "")
            if short_url:
                log(f"ML Link: ✅ {short_url}")
                return short_url
            log(f"ML Link: resposta sem short_url: {data}")
        elif r.status_code == 400:
            # URL não permitida no programa de afiliados — ignorar silenciosamente
            log(f"ML Link: ⚠️ URL não permitida no programa de afiliados (ignorado)")
        else:
            log(f"ML Link: erro {r.status_code} → {r.text[:200]}")
    except Exception as e:
        log(f"ML Link: exceção: {e}")

    return None
