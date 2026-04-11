"""
Mercado Livre — scraping via Playwright (headless Chromium)
Publisher ID: ot20260326074822
"""

import os
import re
import sys
import random
import hashlib
import time

ML_PUBLISHER_ID = os.getenv("ML_PUBLISHER_ID", "ot20260326074822")
PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))

URLS_CATEGORIAS = [
    "https://www.mercadolivre.com.br/ofertas?category=MLB1648",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1051",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1000",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1066",
    "https://www.mercadolivre.com.br/ofertas?category=MLB1039",
    "https://www.mercadolivre.com.br/ofertas#nav-header",
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


def buscar_com_playwright():
    log("ML Playwright: iniciando...")
    try:
        from playwright.sync_api import sync_playwright
        log("ML Playwright: biblioteca OK")
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
                    log(f"ML Playwright: acessando {url[:70]}")
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

                    titulo = page.title()
                    log(f"  -> Pagina: {titulo[:60]}")

                    # Aguarda produtos carregarem (lazy loading)
                    page.wait_for_timeout(2000)
                    # Scroll para forçar carregamento
                    page.evaluate("window.scrollTo(0, 500)")
                    page.wait_for_timeout(2000)

                    # Seletores específicos para cards de produto do ML ofertas
                    cards = []
                    for seletor in [
                        "li.promotion-item",
                        "div.promotion-item",
                        "li[class*='promotion']",
                        "div[class*='promotion-item']",
                        "ol.items_container > li",
                        "section.items_container li",
                    ]:
                        cards = page.query_selector_all(seletor)
                        if cards:
                            log(f"  -> {len(cards)} cards com: {seletor}")
                            break

                    if not cards:
                        log("  -> Nenhum card de produto encontrado — tentando dump da página...")
                        # Mostra estrutura da página para diagnóstico
                        estrutura = page.evaluate("""() => {
                            const els = document.querySelectorAll('li, div, ol, ul, section');
                            const classes = new Set();
                            els.forEach(el => {
                                if (el.className && typeof el.className === 'string') {
                                    el.className.split(' ').forEach(c => {
                                        if (c.includes('item') || c.includes('promo') || c.includes('product') || c.includes('offer'))
                                            classes.add(c);
                                    });
                                }
                            });
                            return Array.from(classes).slice(0, 30).join(', ');
                        }""")
                        log(f"  -> Classes relevantes na página: {estrutura}")
                        continue

                    encontrados = 0
                    for card in cards[:30]:
                        try:
                            # Nome
                            nome_el = card.query_selector("p[class*='title'], h2[class*='title'], span[class*='title'], a[class*='title']")
                            nome = nome_el.inner_text().strip() if nome_el else ""
                            if not nome or len(nome) < 5 or not produto_valido(nome):
                                continue

                            # Pega todos os precos do card
                            precos_el = card.query_selector_all("span.andes-money-amount__fraction")
                            valores = []
                            for pel in precos_el:
                                v = extrair_preco(pel.inner_text())
                                if v >= PRECO_MINIMO:
                                    valores.append(v)

                            if not valores:
                                continue

                            preco      = min(valores)
                            preco_orig = max(valores) if len(valores) > 1 else 0

                            if preco > PRECO_MAXIMO:
                                continue

                            # Desconto
                            desc_el  = card.query_selector("span[class*='discount'], span[class*='rebate'], span[class*='off']")
                            desc_txt = desc_el.inner_text() if desc_el else ""
                            desconto = 0
                            if desc_txt:
                                m = re.search(r'(\d+)', desc_txt)
                                if m:
                                    desconto = int(m.group(1))
                            if desconto == 0 and preco_orig > preco > 0:
                                desconto = int((1 - preco / preco_orig) * 100)

                            # Tag "Mais Vendido" — aumenta score
                            mais_vendido = False
                            tag_el = card.query_selector("span[class*='highlight'], span[class*='tag'], div[class*='badge']")
                            if tag_el:
                                tag_txt = tag_el.inner_text().lower()
                                if "mais vendido" in tag_txt or "best seller" in tag_txt:
                                    mais_vendido = True
                                    log(f"  ⭐ MAIS VENDIDO: {nome[:40]}")

                            # Link
                            link_el = card.query_selector("a")
                            link = link_el.get_attribute("href") if link_el else ""
                            if not link or "mercadolivre" not in link:
                                continue

                            # Imagem
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

                            log(f"  -> OK: {nome[:45]} | R${preco} | {desconto}% {'⭐' if mais_vendido else ''}")
                            produtos.append({
                                "nome":           nome,
                                "preco":          round(preco, 2),
                                "preco_original": round(preco_orig, 2) if preco_orig > preco else 0,
                                "desconto":       desconto,
                                "loja":           "MERCADOLIVRE",
                                "frete":          "🚚 Frete a calcular",
                                "link_afiliado":  link_curto,
                                "imagem_url":     imagem,
                                "score":          3 if mais_vendido else 1,
                                "fontes":         ["mercadolivre"],
                            })
                            encontrados += 1

                        except Exception as e:
                            log(f"  ML card erro: {e}")
                            continue

                    log(f"  -> {encontrados} produtos válidos nesta URL")
                    time.sleep(2)

                except Exception as e:
                    log(f"ML url erro: {e}")
                    continue

            browser.close()

        except Exception as e:
            log(f"ML browser erro: {e}")

    log(f"Mercado Livre (Playwright): {len(produtos)} produtos encontrados")
    return produtos


def buscar_todos_produtos():
    return buscar_com_playwright()
