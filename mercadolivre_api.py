"""
Mercado Livre — scraping via Playwright (headless Chromium)
Publisher ID: ot20260326074822
"""

import os
import re
import random
import hashlib
import time

ML_PUBLISHER_ID = os.getenv("ML_PUBLISHER_ID", "ot20260326074822")
PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

URLS_CATEGORIAS = [
    "https://www.mercadolivre.com.br/ofertas#nav-header",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1648",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1051",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1000",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1066",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1039",
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


def produto_valido(nome):
    nome_lower = nome.lower()
    for p in PALAVRAS_BLOQUEADAS:
        if p in nome_lower:
            return False
    return True


def extrair_preco(texto):
    if not texto:
        return 0.0
    try:
        limpo = re.sub(r'[^\d,.]', '', texto)
        limpo = limpo.replace('.', '').replace(',', '.')
        return float(limpo)
    except:
        return 0.0


def gerar_link_afiliado(url):
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}matt_tool={ML_PUBLISHER_ID}"


def encurtar_link(url_longa):
    try:
        import requests
        r = requests.get(f"https://tinyurl.com/api-create.php?url={url_longa}", timeout=5)
        if r.status_code == 200 and r.text.startswith("https://"):
            return r.text.strip()
    except:
        pass
    return url_longa


import sys

def log(msg):
    """Log com flush imediato para aparecer no Railway."""
    print(msg, flush=True)
    sys.stdout.flush()


def buscar_com_playwright():
    log("ML Playwright: iniciando...")
    try:
        from playwright.sync_api import sync_playwright
        log("ML Playwright: biblioteca importada OK")
    except ImportError as e:
        log(f"ML Playwright: ERRO import — {e}")
        return []

    produtos = []
    vistos   = set()
    urls = random.sample(URLS_CATEGORIAS, min(3, len(URLS_CATEGORIAS)))

    with sync_playwright() as p:
        try:
            log("ML Playwright: lançando browser...")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-zygote",
                    "--single-process",
                ]
            )
            log("ML Playwright: browser OK")
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="pt-BR",
            )
            page = context.new_page()

            for url in urls:
                try:
                    log(f"ML Playwright: acessando {url[:60]}")
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                    # Loga o título da página para confirmar que carregou
                    titulo = page.title()
                    log(f"  -> Página: {titulo[:60]}")

                    # Tenta vários seletores para achar os cards
                    for seletor in ["li.promotion-item", "ol.items_container li", "div.ui-search-layout__item", "li[class*='item']"]:
                        cards = page.query_selector_all(seletor)
                        if cards:
                            log(f"  -> {len(cards)} cards com seletor: {seletor}")
                            break
                    else:
                        log(f"  -> 0 cards encontrados com nenhum seletor!")
                        # Loga o HTML parcial para diagnóstico
                        html = page.content()
                        log(f"  -> HTML snippet: {html[500:1000]}")
                        continue

                    for card in cards[:20]:
                        try:
                            nome_el = card.query_selector("p[class*='title'], h2[class*='title']")
                            nome = nome_el.inner_text().strip() if nome_el else ""
                            if not nome or not produto_valido(nome):
                                continue

                            preco_el = card.query_selector("span.andes-money-amount__fraction")
                            preco = extrair_preco(preco_el.inner_text() if preco_el else "")
                            if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
                                continue

                            orig_el = card.query_selector("s span.andes-money-amount__fraction")
                            preco_orig = extrair_preco(orig_el.inner_text() if orig_el else "")

                            desc_el = card.query_selector("span[class*='discount']")
                            desc_txt = desc_el.inner_text() if desc_el else ""
                            desconto = 0
                            if desc_txt:
                                m = re.search(r'(\d+)', desc_txt)
                                if m:
                                    desconto = int(m.group(1))
                            elif preco_orig > preco > 0:
                                desconto = int((1 - preco / preco_orig) * 100)

                            if desconto < DESCONTO_MINIMO:
                                continue

                            link_el = card.query_selector("a")
                            link = link_el.get_attribute("href") if link_el else ""
                            if not link:
                                continue

                            img_el = card.query_selector("img")
                            imagem = ""
                            if img_el:
                                imagem = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

                            chave = hashlib.md5(nome.encode()).hexdigest()
                            if chave in vistos:
                                continue
                            vistos.add(chave)

                            link_clean    = link.split("#")[0].split("?")[0]
                            link_afiliado = gerar_link_afiliado(link_clean)
                            link_curto    = encurtar_link(link_afiliado)

                            log(f"  -> Produto: {nome[:50]} | R${preco} | {desconto}%")
                            produtos.append({
                                "nome":           nome,
                                "preco":          round(preco, 2),
                                "preco_original": round(preco_orig, 2) if preco_orig > preco else 0,
                                "desconto":       desconto,
                                "loja":           "MERCADOLIVRE",
                                "frete":          "🚚 Frete a calcular",
                                "link_afiliado":  link_curto,
                                "imagem_url":     imagem,
                                "score":          1,
                                "fontes":         ["mercadolivre"],
                            })

                        except Exception as e:
                            log(f"  ML card erro: {e}")
                            continue

                    time.sleep(2)

                except Exception as e:
                    log(f"ML url erro: {e}")
                    continue

            browser.close()

        except Exception as e:
            log(f"ML browser erro: {e}")

    log(f"Mercado Livre (Playwright): {len(produtos)} produtos >= {DESCONTO_MINIMO}% desconto")
    return produtos


def buscar_todos_produtos():
    return buscar_com_playwright()
