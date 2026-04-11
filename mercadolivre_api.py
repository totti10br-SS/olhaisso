"""
Mercado Livre — via ScraperAPI buscando site do ML
Publisher ID: ot20260326074822
"""

import os
import re
import sys
import json
import random
import hashlib
import time
import requests

ML_PUBLISHER_ID = os.getenv("ML_PUBLISHER_ID", "ot20260326074822")
SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY", "")
PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

URLS_BUSCA = [
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1648", "Computação"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1051", "Celulares"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1000", "Eletrônicos"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1066", "TVs"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1039", "Video Games"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1002", "Áudio"),
]

PALAVRAS_BLOQUEADAS = [
    "bola de futebol", "bola gigante", "brinquedo", "brinquedos",
    "roupa", "roupas", "vestido", "camisa", "camiseta",
    "sapato", "sandalia", "bolsa", "carteira",
    "furadeira", "parafusadeira", "martelo", "serra",
    "multimetro", "churrasqueira", "fogueira",
    "cortador de grama", "vaso de planta",
    "suplemento", "creatina", "whey protein", "vitamina",
    "remedio", "medicamento",
]


def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()


def produto_valido(nome):
    nome_lower = nome.lower()
    for p in PALAVRAS_BLOQUEADAS:
        if p in nome_lower:
            return False
    return True


def gerar_link_afiliado(url):
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}matt_tool={ML_PUBLISHER_ID}"


def encurtar_link(url_longa):
    try:
        r = requests.get(f"https://tinyurl.com/api-create.php?url={url_longa}", timeout=5)
        if r.status_code == 200 and r.text.startswith("https://"):
            return r.text.strip()
    except:
        pass
    return url_longa


def scraper_fetch(url):
    """Busca HTML via ScraperAPI."""
    try:
        payload = {
            "api_key":      SCRAPERAPI_KEY,
            "url":          url,
            "country_code": "br",
            "render":       "false",
        }
        r = requests.get("https://api.scraperapi.com", params=payload, timeout=60)
        log(f"  ScraperAPI {r.status_code} → {url[:60]}")
        if r.status_code == 200:
            return r.text
        log(f"  Erro: {r.text[:150]}")
        return None
    except Exception as e:
        log(f"  ScraperAPI erro: {e}")
        return None


def extrair_produtos_html(html):
    """Extrai produtos do JSON embutido no HTML do ML."""
    if not html:
        return []

    log(f"  -> HTML recebido: {len(html)} chars")

    # ML injeta dados no formato: {"results":[...]} dentro de scripts
    # Procura por blocos JSON que contenham "original_price" (indica produto com desconto)
    try:
        # Tenta achar o JSON principal da página
        idx = html.find('"results":[{')
        if idx == -1:
            idx = html.find('"items":[{')

        if idx != -1:
            # Encontra o início do array
            start = html.rfind('[', 0, idx + 15)
            if start == -1:
                start = idx + html[idx:].find('[')

            # Encontra o fim balanceado do array
            depth = 0
            end = start
            for i, c in enumerate(html[start:], start):
                if c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
                if i - start > 500000:  # limite de segurança
                    break

            json_str = html[start:end]
            data = json.loads(json_str)
            if isinstance(data, list) and len(data) > 0:
                log(f"  -> {len(data)} itens extraídos do JSON")
                return data
    except Exception as e:
        log(f"  -> Erro ao extrair JSON: {e}")

    # Fallback: conta links do ML para diagnóstico
    links = re.findall(r'href="(https://www\.mercadolivre\.com\.br/[^"?#]+)"', html)
    links_unicos = list(set(links))
    log(f"  -> JSON não encontrado. {len(links_unicos)} links de produto no HTML")
    if links_unicos:
        log(f"  -> Exemplo: {links_unicos[0][:80]}")

    return []


def processar_item(item):
    try:
        if not isinstance(item, dict):
            return None

        nome = item.get("title", "").strip()
        if not nome or not produto_valido(nome):
            return None

        preco      = float(item.get("price", 0) or 0)
        preco_orig = float(item.get("original_price") or 0)

        if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None

        desconto = 0
        if preco_orig > preco:
            desconto = int((1 - preco / preco_orig) * 100)

        if desconto < DESCONTO_MINIMO:
            return None

        permalink = item.get("permalink", "")
        if not permalink:
            return None

        tags = [t.get("id", "") for t in item.get("tags", [])]
        mais_vendido = "best_seller" in tags

        shipping     = item.get("shipping", {}) or {}
        frete_gratis = shipping.get("free_shipping", False)
        frete_txt    = "✅ Frete grátis" if frete_gratis else "🚚 Frete a calcular"

        thumbnail = item.get("thumbnail", "")
        imagem    = thumbnail.replace("I.jpg", "O.jpg") if thumbnail else ""

        link_afiliado = gerar_link_afiliado(permalink)
        link_curto    = encurtar_link(link_afiliado)

        if mais_vendido:
            log(f"  ⭐ MAIS VENDIDO: {nome[:40]}")

        return {
            "nome":           nome,
            "preco":          round(preco, 2),
            "preco_original": round(preco_orig, 2) if preco_orig > preco else 0,
            "desconto":       desconto,
            "loja":           "MERCADOLIVRE",
            "frete":          frete_txt,
            "link_afiliado":  link_curto,
            "imagem_url":     imagem,
            "score":          3 if mais_vendido else 1,
            "fontes":         ["mercadolivre"],
        }
    except Exception as e:
        log(f"  ML item erro: {e}")
        return None


def buscar_todos_produtos():
    if not SCRAPERAPI_KEY:
        log("ML ScraperAPI: SCRAPERAPI_KEY não configurada")
        return []

    log("ML ScraperAPI: iniciando busca...")
    todos   = []
    vistos  = set()
    total_bruto = 0

    urls = random.sample(URLS_BUSCA, min(4, len(URLS_BUSCA)))

    for url, nome in urls:
        try:
            log(f"ML buscando: {nome}")
            html = scraper_fetch(url)
            items = extrair_produtos_html(html)
            total_bruto += len(items)

            # Debug — mostra estrutura do primeiro item
            if items and len(todos) == 0:
                primeiro = items[0] if isinstance(items[0], dict) else {}
                log(f"  -> Campos do item: {list(primeiro.keys())[:10]}")
                log(f"  -> title={primeiro.get('title','')[:40]} price={primeiro.get('price')} orig={primeiro.get('original_price')} permalink={str(primeiro.get('permalink',''))[:50]}")

            for item in items:
                p = processar_item(item)
                if p:
                    chave = hashlib.md5(p["nome"].encode()).hexdigest()
                    if chave not in vistos:
                        vistos.add(chave)
                        todos.append(p)
            time.sleep(2)
        except Exception as e:
            log(f"ML erro {nome}: {e}")
            continue

    log(f"Mercado Livre (ScraperAPI): {total_bruto} brutos → {len(todos)} válidos")
    return todos
