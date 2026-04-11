"""
Mercado Livre — via ScraperAPI + API oficial do ML
Publisher ID: ot20260326074822
ScraperAPI bypassa o 403 do ML
"""

import os
import re
import sys
import random
import hashlib
import time
import requests

ML_PUBLISHER_ID = os.getenv("ML_PUBLISHER_ID", "ot20260326074822")
SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY", "")
PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

# Categorias tech do ML Brasil
CATEGORIAS = [
    ("MLB1648", "Computação"),
    ("MLB1676", "Monitores"),
    ("MLB1051", "Celulares"),
    ("MLB1000", "Eletrônicos"),
    ("MLB1066", "TVs"),
    ("MLB1039", "Video Games"),
    ("MLB1002", "Áudio"),
    ("MLB1132", "Câmeras"),
]

KEYWORDS = [
    "monitor gamer 144hz",
    "monitor 4k",
    "ssd nvme 1tb",
    "memoria ram ddr4",
    "placa de video",
    "processador intel",
    "processador amd",
    "smartphone samsung",
    "iphone",
    "xiaomi redmi",
    "motorola edge",
    "notebook gamer",
    "teclado mecanico",
    "mouse gamer",
    "headset gamer",
    "smart tv 4k",
    "playstation 5",
    "xbox series",
    "nintendo switch",
    "robo aspirador",
    "airfryer",
    "smartwatch",
    "fonte pc 650w",
    "placa mae",
    "cooler cpu",
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
        r = requests.get(
            f"https://tinyurl.com/api-create.php?url={url_longa}",
            timeout=5
        )
        if r.status_code == 200 and r.text.startswith("https://"):
            return r.text.strip()
    except:
        pass
    return url_longa


def scraper_get(url):
    """Faz requisição via ScraperAPI para bypasear o 403 do ML."""
    try:
        payload = {
            "api_key": SCRAPERAPI_KEY,
            "url":     url,
            "country_code": "br",
        }
        r = requests.get(
            "https://api.scraperapi.com",
            params=payload,
            timeout=30
        )
        log(f"  ScraperAPI status: {r.status_code} para {url[:60]}")
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        log(f"  ScraperAPI erro: {e}")
        return None


def processar_item(item):
    """Converte item da API ML no formato padrão do bot."""
    try:
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

        # Tag mais vendido
        tags = [t.get("id", "") for t in item.get("tags", [])]
        mais_vendido = "best_seller" in tags or "good_sale_quality" in tags

        shipping    = item.get("shipping", {}) or {}
        frete_gratis = shipping.get("free_shipping", False)
        frete_txt   = "✅ Frete grátis" if frete_gratis else "🚚 Frete a calcular"

        thumbnail   = item.get("thumbnail", "")
        imagem      = thumbnail.replace("I.jpg", "O.jpg") if thumbnail else ""

        link_afiliado = gerar_link_afiliado(permalink)
        link_curto    = encurtar_link(link_afiliado)

        if mais_vendido:
            log(f"  ⭐ MAIS VENDIDO: {nome[:45]}")

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
        log(f"  ML processar item erro: {e}")
        return None


def buscar_por_categoria(cat_id, cat_nome, limit=10):
    """Busca produtos em oferta por categoria via ScraperAPI."""
    url = f"https://api.mercadolibre.com/sites/MLB/search?category={cat_id}&sort=best_seller&limit={limit}"
    log(f"ML buscando categoria: {cat_nome}")
    data = scraper_get(url)
    if not data:
        return []
    items = data.get("results", [])
    log(f"  -> {len(items)} itens retornados")
    return items


def buscar_por_keyword(keyword, limit=8):
    """Busca produtos por keyword via ScraperAPI."""
    url = f"https://api.mercadolibre.com/sites/MLB/search?q={requests.utils.quote(keyword)}&sort=best_seller&limit={limit}"
    data = scraper_get(url)
    if not data:
        return []
    return data.get("results", [])


def buscar_todos_produtos():
    if not SCRAPERAPI_KEY:
        log("ML ScraperAPI: SCRAPERAPI_KEY não configurada")
        return []

    log("ML ScraperAPI: iniciando busca...")
    todos  = []
    vistos = set()
    total_bruto = 0

    # Busca por categorias
    cats = random.sample(CATEGORIAS, min(4, len(CATEGORIAS)))
    for cat_id, cat_nome in cats:
        try:
            items = buscar_por_categoria(cat_id, cat_nome, limit=10)
            total_bruto += len(items)
            for item in items:
                p = processar_item(item)
                if p:
                    chave = hashlib.md5(p["nome"].encode()).hexdigest()
                    if chave not in vistos:
                        vistos.add(chave)
                        todos.append(p)
            time.sleep(1)
        except Exception as e:
            log(f"ML categoria {cat_nome} erro: {e}")
            continue

    # Busca por keywords
    kws = random.sample(KEYWORDS, min(6, len(KEYWORDS)))
    for kw in kws:
        try:
            items = buscar_por_keyword(kw, limit=8)
            total_bruto += len(items)
            for item in items:
                p = processar_item(item)
                if p:
                    chave = hashlib.md5(p["nome"].encode()).hexdigest()
                    if chave not in vistos:
                        vistos.add(chave)
                        todos.append(p)
            time.sleep(1)
        except Exception as e:
            log(f"ML keyword '{kw}' erro: {e}")
            continue

    log(f"Mercado Livre (ScraperAPI): {total_bruto} brutos → {len(todos)} com desconto >= {DESCONTO_MINIMO}%")
    return todos
