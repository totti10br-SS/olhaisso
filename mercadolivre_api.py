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
        log(f"  Erro: {r.text[:100]}")
        return None
    except Exception as e:
        log(f"  ScraperAPI erro: {e}")
        return None


def extrair_produtos_html(html):
    if not html:
        return []
    log(f"  -> HTML: {len(html)} chars")
    try:
        idx = html.find('"results":[{')
        if idx == -1:
            idx = html.find('"items":[{')
        if idx == -1:
            log("  -> JSON não encontrado")
            return []
        start = html.rfind('[', 0, idx + 15)
        depth = 0
        end = start
        for i, c in enumerate(html[start:], start):
            if c == '[': depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            if i - start > 500000:
                break
        data = json.loads(html[start:end])
        if isinstance(data, list) and len(data) > 0:
            log(f"  -> {len(data)} itens extraídos")
            return data
    except Exception as e:
        log(f"  -> Erro JSON: {e}")
    return []


def processar_item(item):
    try:
        if not isinstance(item, dict):
            return None

        card = item.get("card", {})
        if not card:
            return None

        metadata   = card.get("metadata", {}) or {}
        components = card.get("components", []) or []
        pictures   = card.get("pictures", []) or []

        # Debug primeiro item
        if not getattr(processar_item, '_logged', False):
            processar_item._logged = True
            log(f"  -> metadata: {list(metadata.keys())}")
            log(f"  -> {len(components)} components")
            for c in components:
                ctype = c.get("type","")
                cdata = c.get(ctype, c)
                log(f"     [{ctype}] → {str(cdata)[:150]}")

        # URL do produto
        url_prod = metadata.get("url", "")
        if url_prod and not url_prod.startswith("http"):
            url_prod = "https://" + url_prod
        if not url_prod:
            return None

        # Extrai dados dos components
        nome       = ""
        preco      = 0.0
        preco_orig = 0.0
        desconto   = 0
        imagem     = ""
        mais_vendido = False
        frete_ok   = False

        for comp in components:
            if not isinstance(comp, dict):
                continue
            ctype = comp.get("type", "").lower()
            cdata = comp.get(ctype, {})
            if not isinstance(cdata, dict):
                cdata = {}

            if ctype == "title":
                nome = cdata.get("text", "") or nome

            elif ctype == "price":
                curr = cdata.get("current_price", {}) or {}
                prev = cdata.get("previous_price", {}) or {}
                preco      = float(curr.get("value", 0) or 0)
                preco_orig = float(prev.get("value", 0) or 0)
                log(f"  -> PRICE: curr={preco} orig={preco_orig} cdata_keys={list(cdata.keys())[:5]}")

            elif ctype == "shipping":
                frete_txt_comp = cdata.get("text", "")
                if "grátis" in frete_txt_comp.lower() or "gratis" in frete_txt_comp.lower():
                    frete_ok = True

            elif ctype in ("image", "picture", "gallery"):
                imagem = cdata.get("url", "") or cdata.get("src", "") or imagem

            elif ctype == "highlight":
                txt = cdata.get("text", "").lower()
                if "mais vendido" in txt or "best seller" in txt:
                    mais_vendido = True

        # Imagem: vem em card["pictures"], não nos components
        if not getattr(processar_item, '_img_logged', False):
            processar_item._img_logged = True
            log(f"  -> pictures raw: {str(pictures)[:300]}")
        if not imagem and pictures:
            try:
                primeira = pictures[0]
                if isinstance(primeira, dict):
                    imagem = primeira.get("url", "") or primeira.get("src", "") or ""
                elif isinstance(primeira, str):
                    imagem = primeira
            except Exception:
                imagem = ""
        if not getattr(processar_item, '_img2_logged', False):
            processar_item._img2_logged = True
            log(f"  -> imagem_url: '{imagem[:120] if imagem else "VAZIO"}'")

        # Fallback nome
        if not nome:
            nome = metadata.get("title", "")

        nome = nome.strip()
        if not nome or not produto_valido(nome):
            return None

        if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None

        if preco_orig > preco and desconto == 0:
            desconto = int((1 - preco / preco_orig) * 100)

        if desconto < DESCONTO_MINIMO:
            return None

        frete_txt     = "✅ Frete grátis" if frete_ok else "🚚 Frete a calcular"
        link_afiliado = gerar_link_afiliado(url_prod)
        link_curto    = encurtar_link(link_afiliado)

        log(f"  ✅ {nome[:45]} | R${preco} | {desconto}% {'⭐' if mais_vendido else ''}")

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
        import traceback
        log(f"  ML item erro: {e} | {traceback.format_exc()[-300:]}")
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
            html  = scraper_fetch(url)
            items = extrair_produtos_html(html)
            total_bruto += len(items)

            if items and len(todos) == 0:
                # Debug primeiro item
                processar_item._logged = False

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
