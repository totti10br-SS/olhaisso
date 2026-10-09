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
SCRAPINGANT_KEY = os.getenv("SCRAPINGANT_KEY", "")
ZENROWS_KEY     = os.getenv("ZENROWS_KEY", "")      # fallback
SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY", "")   # fallback
PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

URLS_BUSCA = [
    ("https://lista.mercadolivre.com.br/computacao/notebooks-acessorios/_OrderId_PRICE*DESC_Discount_30-100_NoIndex_True", "Notebooks"),
    ("https://lista.mercadolivre.com.br/celulares-telefones/celulares-smartphones/_OrderId_PRICE*DESC_Discount_25-100_NoIndex_True", "Smartphones"),
    ("https://lista.mercadolivre.com.br/eletronicos-audio-video/televisores/_OrderId_PRICE*DESC_Discount_30-100_NoIndex_True", "TVs"),
    ("https://lista.mercadolivre.com.br/video-games/controles/_OrderId_PRICE*DESC_Discount_20-100_NoIndex_True", "Controles"),
    ("https://lista.mercadolivre.com.br/video-games/videogames/_OrderId_PRICE*DESC_Discount_20-100_NoIndex_True", "Consoles"),
    ("https://lista.mercadolivre.com.br/video-games/jogos-videogame/_OrderId_PRICE*DESC_Discount_20-100_NoIndex_True", "Jogos"),
    ("https://lista.mercadolivre.com.br/eletronicos-audio-video/audio/fones-ouvido/_OrderId_PRICE*DESC_Discount_25-100_NoIndex_True", "Fones"),
    ("https://lista.mercadolivre.com.br/informatica/monitores-telas/_OrderId_PRICE*DESC_Discount_25-100_NoIndex_True", "Monitores"),
]

PALAVRAS_BLOQUEADAS = [
    # Ferramentas e equipamentos industriais
    "guincho", "girafa", "talha", "macaco hidraulico", "compressor",
    "furadeira", "parafusadeira", "martelo", "serra", "esmerilhadeira",
    "retifica", "lixadeira", "soldador", "solda", "torno",
    "andaime", "escada", "carrinho de mao", "empilhadeira",
    # Iluminação não-tech / cenografia
    "lente de projecao", "lente spot", "filtro efeito", "gobo",
    "refletor par", "moving head", "beam", "follow spot",
    "canhao de luz", "strobo", "maquina de fumaca",
    # Automotivo
    "pneu", "rodas", "amortecedor", "escapamento", "farol",
    "retrovisor", "para-choque", "capota", "banco de carro",
    # Casa e jardim
    "cortador de grama", "vaso de planta", "mangueira",
    "churrasqueira", "fogueira", "fogao", "geladeira", "lava-roupa",
    "maquina de lavar", "secadora", "lava-loucas",
    "sofa", "colchao", "cama", "guarda-roupa", "estante",
    "tapete", "cortina", "persiana", "luminaria de teto",
    # Vestuário e moda
    "roupa", "roupas", "vestido", "camisa", "camiseta", "blusa",
    "calca", "bermuda", "short", "saia", "jaqueta", "casaco",
    "sapato", "tenis", "sandalia", "chinelo", "bota",
    "bolsa", "mochila", "mala", "carteira", "cinto",
    # Brinquedos e esportes
    "bola de futebol", "bola gigante", "brinquedo", "brinquedos",
    "boneca", "carrinho de brinquedo", "lego",
    "bicicleta", "patins", "skate", "patinete infantil",
    # Saúde e beleza
    "suplemento", "creatina", "whey protein", "vitamina",
    "remedio", "medicamento", "termometro clinico",
    "perfume", "fragrancia", "eau de parfum", "colonia",
    "shampoo", "condicionador", "creme", "hidratante",
    "maquiagem", "batom", "base", "sombra", "rimel",
    # Optica / astronomia não-tech
    "telescopio", "telescópio", "luneta", "microscopio",
    # Animais
    "racao", "casinha de cachorro", "aquario", "gaiola",
    # Livros e papelaria
    "livro", "album de figurinha", "figurinha",
    "caderno", "agenda", "caneta", "lapis",
]


def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()


# Palavras que DEVEM aparecer em produtos tech (se não tiver nenhuma, bloqueia)
PALAVRAS_TECH = [
    "notebook", "laptop", "pc", "computador", "desktop",
    "celular", "smartphone", "iphone", "samsung", "xiaomi", "motorola",
    "tv", "smart tv", "televisao", "televisão",
    "monitor", "tela", "display",
    "tablet", "ipad",
    "fone", "headset", "headphone", "earphone", "auricular", "caixa de som",
    "soundbar", "speaker",
    "teclado", "mouse", "mousepad",
    "ssd", "hd externo", "pendrive", "memoria ram", "processador",
    "placa de video", "placa mae", "gabinete", "fonte atx",
    "roteador", "repetidor wifi", "modem", "switch",
    "camera", "webcam", "impressora",
    "carregador", "cabo usb", "hub usb", "adaptador",
    "controle", "joystick", "videogame", "playstation", "xbox", "nintendo",
    "ps5", "ps4", "dualsense", "dual sense", "switch 2", "switch2",
    "jogo ps5", "jogo xbox", "jogo nintendo", "game ps5", "game xbox",
    "headset gamer", "fone gamer", "console gamer",
    "smartwatch", "relogio inteligente",
    "drone", "gopro", "action cam",
    "power bank", "nobreak", "estabilizador",
    "ar condicionado", "ventilador tower", "purificador de ar",
    "fritadeira air fryer", "cafeteira", "liquidificador",
]

def produto_valido(nome):
    nome_lower = nome.lower()
    # Verifica palavras bloqueadas
    for p in PALAVRAS_BLOQUEADAS:
        if p in nome_lower:
            log(f"  🚫 Bloqueado ({p}): {nome[:50]}")
            return False
    return True

def produto_e_tech(nome):
    """Verifica se o produto tem ao menos uma palavra-chave tech."""
    nome_lower = nome.lower()
    for p in PALAVRAS_TECH:
        if p in nome_lower:
            return True
    return False


def gerar_link_afiliado(url):
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}matt_tool={ML_PUBLISHER_ID}"


TINYURL_API_TOKEN = os.getenv("TINYURL_API_TOKEN", "5E6O0b6FW8c5FDRCSjjo1TBl4VO0JtmUwgDgtVr7opF1vCMzdu5NCD1f7T5k")

def encurtar_link(url_longa):
    try:
        r = requests.post(
            "https://api.tinyurl.com/create",
            headers={
                "Authorization": f"Bearer {TINYURL_API_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"url": url_longa, "domain": "tinyurl.com"},
            timeout=8,
        )
        if r.status_code == 200:
            short = r.json().get("data", {}).get("tiny_url", "")
            if short.startswith("http"):
                return short
    except:
        pass
    return url_longa


def _is_captcha_html(html):
    """Detecta se o HTML retornado é página de CAPTCHA do ML."""
    if not html:
        return True
    # Busca no HTML inteiro (não só nos primeiros 5000 chars)
    # O ML embute o CAPTCHA num JSON no meio da página
    captcha_signs = ["Cerrar", "REINTENTAR", "Reintentar", "robot", "captcha", "distil_r_captcha"]
    lower = html.lower()
    for sign in captcha_signs:
        if sign.lower() in lower:
            return True
    # Também detecta pela ausência de qualquer chave de produto conhecida
    # quando o HTML parece ser página de erro (< 60KB sem nenhuma chave de produto)
    if len(html) < 60000:
        tem_produto = any(f'"{k}"' in html for k in ["results", "items", "elements", "offers", "products", "deals", "card", "title", "ui-search"])
        if not tem_produto:
            return True
    return False


def _scrapingant_get(url, browser, proxy_country, timeout=90):
    """Faz uma requisição ao ScrapingAnt e retorna (status_code, html) ou (None, None) em erro."""
    params = {
        "url":       url,
        "x-api-key": SCRAPINGANT_KEY,
        "browser":   browser,
    }
    if proxy_country:
        params["proxy_country"] = proxy_country
    try:
        r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        log(f"  ScrapingAnt erro: {e}")
        return None, None


def _url_sem_filtros(url):
    """Retorna versão da URL sem os filtros _NoIndex_ e _Discount_ (menos suspeita para o ML)."""
    # Remove tudo a partir de _OrderId_ ou _Discount_ ou _NoIndex_
    import re as _re
    url_limpa = _re.sub(r'/_Order[^"]*', '', url)
    url_limpa = _re.sub(r'/_Discount[^"]*', '', url_limpa)
    url_limpa = _re.sub(r'/_NoIndex[^"]*', '', url_limpa)
    return url_limpa.rstrip('/')


def scraper_fetch(url):
    # ScrapingAnt — tenta 4 configs; se todas falharem com CAPTCHA,
    # tenta URL alternativa sem filtros (menos sinalizável) com browser=true
    if SCRAPINGANT_KEY:
        configs = [
            {"browser": "false", "proxy_country": "BR"},
            {"browser": "true",  "proxy_country": "BR"},
            {"browser": "false", "proxy_country": "US"},
            {"browser": "true",  "proxy_country": "US"},
        ]
        captcha_count = 0
        for cfg in configs:
            bmode    = cfg["browser"]
            pcountry = cfg.get("proxy_country", "")
            status, html = _scrapingant_get(url, bmode, pcountry)
            if status is None:
                break  # exceção de rede — para
            log(f"  ScrapingAnt browser={bmode} proxy={pcountry} {status} → {url[:55]}")
            if status in (401, 402, 403):
                log(f"  ScrapingAnt erro auth/quota {status} — parando")
                break  # erro de auth/quota — não tenta de novo
            if status != 200:
                log(f"  ScrapingAnt erro HTTP {status} — próxima config...")
                continue  # erro técnico (422, 500, etc) — tenta próxima config
            if _is_captcha_html(html):
                log(f"  ScrapingAnt CAPTCHA detectado (browser={bmode} proxy={pcountry}) — próxima config...")
                captcha_count += 1
                continue
            # HTML OK
            if len(html) > 80000:
                return html
            tem_json = any(f'"{k}":[{{' in html for k in ["results","items","elements","offers","products","deals"])
            if tem_json:
                return html
            if len(html) > 10000:
                return html
            log(f"  ScrapingAnt HTML muito pequeno ({len(html)} chars) — próxima config...")

        # Se todas as configs falharam por CAPTCHA, tenta URL sem filtros com browser=true
        if captcha_count >= 2:
            url_alt = _url_sem_filtros(url)
            if url_alt != url:
                log(f"  Tentando URL sem filtros: {url_alt[:60]}")
                for pcountry in ["BR", "US"]:
                    status, html = _scrapingant_get(url_alt, "true", pcountry, timeout=90)
                    if status is None:
                        break
                    log(f"  ScrapingAnt URL-alt browser=true proxy={pcountry} {status}")
                    if status in (401, 402, 403):
                        break
                    if status != 200:
                        log(f"  URL-alt erro HTTP {status} — próxima config...")
                        continue
                    if not _is_captcha_html(html) and len(html) > 10000:
                        log(f"  ✅ URL-alt funcionou!")
                        return html
                    log(f"  URL-alt CAPTCHA (proxy={pcountry})")


    # Fallback ZenRows
    if ZENROWS_KEY:
        try:
            params = {
                "url":           url,
                "apikey":        ZENROWS_KEY,
                "js_render":     "false",
                "antibot":       "true",
                "premium_proxy": "true",
                "proxy_country": "br",
            }
            r = requests.get("https://api.zenrows.com/v1/", params=params, timeout=60)
            log(f"  ZenRows {r.status_code} → {url[:60]}")
            if r.status_code == 200:
                return r.text
            log(f"  ZenRows erro: {r.text[:100]}")
        except Exception as e:
            log(f"  ZenRows erro: {e}")

    # Fallback ScraperAPI
    if SCRAPERAPI_KEY:
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
        except Exception as e:
            log(f"  ScraperAPI erro: {e}")

    return None


def _extrair_lista_json(html, chave):
    """Tenta extrair lista JSON pela chave dentro do HTML."""
    idx = html.find(f'"{chave}":[{{')
    if idx == -1:
        idx = html.find(f'"{chave}": [{{')
    if idx == -1:
        return []
    start = html.find('[', idx)
    if start == -1:
        return []
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
    try:
        data = json.loads(html[start:end])
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass
    return []


def extrair_produtos_html_lista(html):
    """Parser HTML direto para lista.mercadolivre.com.br — extrai produtos das tags HTML."""
    if not html or len(html) < 5000:
        return []
    produtos = []
    try:
        # Padrão: <li class="ui-search-layout__item">...</li>
        # Nome: <h2 class="ui-search-item__title">NOME</h2>
        # Preço atual: <span class="andes-money-amount__fraction">VALOR</span>
        # Desconto: <span class="andes-badge__content">N% OFF</span>
        # Link: <a class="ui-search-link" href="...">
        # Imagem: <img class="ui-search-result-image__element" src="..." / data-src="...">
        import html as htmllib

        nome_pattern = re.compile(r'class="[^"]*ui-search-item__title[^"]*"[^>]*>([^<]+)<', re.IGNORECASE)
        preco_pattern = re.compile(r'class="[^"]*andes-money-amount__fraction[^"]*"[^>]*>([0-9.,]+)<', re.IGNORECASE)
        desconto_pattern = re.compile(r'(\d+)%\s*OFF', re.IGNORECASE)
        link_pattern = re.compile(r'class="[^"]*ui-search-link[^"]*"\s+href="([^"]+)"', re.IGNORECASE)
        img_pattern = re.compile(r'class="[^"]*ui-search-result-image__element[^"]*"[^>]+(?:data-src|src)="([^"]+)"', re.IGNORECASE)

        nomes = nome_pattern.findall(html)
        precos = preco_pattern.findall(html)
        descontos = desconto_pattern.findall(html)
        links = link_pattern.findall(html)
        imagens = img_pattern.findall(html)

        if not nomes or not precos:
            return []

        log(f"  -> HTML lista: {len(nomes)} nomes, {len(precos)} preços, {len(descontos)} descontos")

        for i, nome in enumerate(nomes):
            nome = htmllib.unescape(nome).strip()
            if not nome or len(nome) < 5:
                continue
            preco_txt = precos[i] if i < len(precos) else ""
            if not preco_txt:
                continue
            try:
                preco = float(preco_txt.replace(".", "").replace(",", "."))
            except Exception:
                continue
            desconto = int(descontos[i]) if i < len(descontos) else 0
            url_prod = links[i] if i < len(links) else ""
            imagem = imagens[i] if i < len(imagens) else ""
            # Monta dict no formato que processar_item espera — aqui fazemos direto
            produtos.append({
                "_raw_html": True,
                "nome": nome,
                "preco": preco,
                "preco_original": round(preco / (1 - desconto / 100), 2) if desconto > 0 else 0,
                "desconto": desconto,
                "url_prod": url_prod,
                "imagem": imagem,
            })
    except Exception as e:
        log(f"  HTML lista parse erro: {e}")
    return produtos


def extrair_produtos_html(html):
    if not html:
        return []
    log(f"  -> HTML: {len(html)} chars")

    # Tenta múltiplas chaves candidatas — ML muda o formato com frequência
    CHAVES_CANDIDATAS = [
        "results", "items", "elements", "offers", "products",
        "searchResults", "itemsList", "deals", "promotions",
    ]
    for chave in CHAVES_CANDIDATAS:
        data = _extrair_lista_json(html, chave)
        if data:
            log(f"  -> {len(data)} itens extraídos (chave: '{chave}')")
            return data

    # Fallback: procura qualquer lista grande de objetos com campo "card" ou "title"
    for kw in ['"card":{', '"card": {', '"title":{', '"title": {']:
        idx = html.find(kw)
        if idx > 0:
            # Acha o array pai
            start = html.rfind('[', 0, idx)
            if start > 0:
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
                try:
                    data = json.loads(html[start:end])
                    if isinstance(data, list) and len(data) > 0:
                        log(f"  -> {len(data)} itens extraídos (fallback kw: '{kw}')")
                        return data
                except Exception:
                    pass

    # Debug: mostra quais chaves JSON existem no HTML para diagnóstico
    chaves_encontradas = set(re.findall(r'"(\w+)":\s*\[', html))
    log(f"  -> JSON não encontrado. Chaves disponíveis: {sorted(chaves_encontradas)[:30]}")
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

        # ID do item (para link de afiliado oficial)
        item_id = metadata.get("id", "")

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

                # Novo formato ML: preco original em price_labels -> values -> price -> value
                if preco_orig == 0:
                    for lbl in cdata.get("price_labels", []):
                        if "previous_price" in lbl.get("text", ""):
                            for v in lbl.get("values", []):
                                if v.get("key") == "previous_price":
                                    try:
                                        preco_orig = float(v.get("price", {}).get("value", 0) or 0)
                                    except:
                                        pass
                                    break
                            break

                # Fallback: discount_polylabel tem o percentual de desconto
                if preco_orig == 0 and preco > 0:
                    import re as _re
                    dpoly = cdata.get("discount_polylabel", {}) or {}
                    disc_txt = str(dpoly.get("text", "") or "")
                    m_disc = _re.search(r"(\d+)", disc_txt)
                    if m_disc:
                        disc_pct = int(m_disc.group(1))
                        if 5 <= disc_pct <= 90:
                            preco_orig = round(preco / (1 - disc_pct / 100), 2)

                log(f"  -> PRICE: curr={preco} orig={preco_orig}")

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

        # Imagem: vem em card["pictures"]["pictures"][0]["id"]
        if not imagem and isinstance(pictures, dict):
            try:
                pics_list = pictures.get("pictures", [])
                if pics_list and isinstance(pics_list[0], dict):
                    pic_id = pics_list[0].get("id", "")
                    if pic_id:
                        imagem = f"https://http2.mlstatic.com/D_NQ_NP_{pic_id}-F.jpg"
            except Exception:
                imagem = ""

        # Fallback nome
        if not nome:
            nome = metadata.get("title", "")

        nome = nome.strip()
        if not nome:
            return None
        if not produto_valido(nome):
            return None
        if not produto_e_tech(nome):
            log(f"  🚫 Não-tech: {nome[:50]}")
            return None

        if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None

        if preco_orig > preco and desconto == 0:
            desconto = int((1 - preco / preco_orig) * 100)

        if desconto < DESCONTO_MINIMO:
            return None

        frete_txt = "✅ Frete grátis" if frete_ok else "🚚 Frete a calcular"
        # Gera link meli.la via endpoint oficial; fallback para tinyurl se falhar
        try:
            from mercadolivre_link import gerar_link_afiliado_ml
            link_curto = gerar_link_afiliado_ml(url_prod, item_id) or encurtar_link(gerar_link_afiliado(url_prod))
        except Exception:
            link_curto = encurtar_link(gerar_link_afiliado(url_prod))

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


def _processar_item_html(item_raw):
    """Processa produto já extraído do HTML de lista.mercadolivre.com.br."""
    try:
        nome = item_raw.get("nome", "").strip()
        if not nome:
            return None
        if not produto_valido(nome):
            return None
        if not produto_e_tech(nome):
            log(f"  🚫 Não-tech (lista): {nome[:50]}")
            return None
        preco = item_raw.get("preco", 0)
        if preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None
        desconto = item_raw.get("desconto", 0)
        if desconto < DESCONTO_MINIMO:
            return None
        preco_orig = item_raw.get("preco_original", 0)
        url_prod = item_raw.get("url_prod", "")
        imagem = item_raw.get("imagem", "")
        if not url_prod:
            return None
        link_curto = encurtar_link(gerar_link_afiliado(url_prod))
        log(f"  ✅ {nome[:45]} | R${preco} | {desconto}%")
        return {
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
        }
    except Exception as e:
        log(f"  ML HTML item erro: {e}")
        return None


# Mapeamento categoria MLB → URLs de busca
_ML_API_CATEGORIAS = [
    ("MLB1648", "Notebooks"),
    ("MLB1051", "Smartphones"),
    ("MLB1066", "TVs"),
    ("MLB1039", "Controles"),
    ("MLB1144", "Consoles"),
    ("MLB1367", "Jogos"),
    ("MLB1000", "Fones"),
    ("MLB1648", "Monitores"),
]

def _buscar_ml_api_categoria(category_id, nome_cat, desconto_min=None, limit=50):
    """Stub — não usada."""
    return []


def buscar_todos_produtos():
    if not SCRAPINGANT_KEY and not ZENROWS_KEY and not SCRAPERAPI_KEY:
        log("ML: nenhuma chave de scraping configurada")
        return []

    log("ML ScrapingAnt: iniciando busca...")
    todos   = []
    vistos  = set()
    total_bruto = 0

    # Garante que Games sempre entram — resto sorteia
    url_games  = [(u, n) for u, n in URLS_BUSCA if any(g in n.lower() for g in ["games", "consoles", "jogos", "controles"])]
    url_outros = [(u, n) for u, n in URLS_BUSCA if (u, n) not in url_games]
    urls = url_games + random.sample(url_outros, min(3, len(url_outros)))

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
                if item.get("_raw_html"):
                    p = _processar_item_html(item)
                else:
                    p = processar_item(item)
                if p:
                    chave = hashlib.md5(p["nome"].encode()).hexdigest()
                    if chave not in vistos:
                        vistos.add(chave)
                        todos.append(p)

            # Se JSON não funcionou, tenta parser HTML direto
            if not items:
                items_html = extrair_produtos_html_lista(html)
                if items_html:
                    log(f"  -> Fallback HTML lista: {len(items_html)} itens")
                    total_bruto += len(items_html)
                    for item in items_html:
                        p = _processar_item_html(item)
                        if p:
                            chave = hashlib.md5(p["nome"].encode()).hexdigest()
                            if chave not in vistos:
                                vistos.add(chave)
                                todos.append(p)

            time.sleep(2)
        except Exception as e:
            log(f"ML erro {nome}: {e}")
            continue

    log(f"Mercado Livre (ScrapingAnt): {total_bruto} brutos → {len(todos)} válidos")
    return todos


# URLs extras para busca profunda ML
URLS_BUSCA_EXTRA = [
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1648&q=notebook", "Notebooks"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1648&q=monitor+gamer", "Monitores Gamer"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1648&q=ssd+nvme", "SSDs"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1648&q=placa+de+video", "Placas de Vídeo"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1051&q=smartphone+samsung", "Samsung"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1051&q=smartphone+motorola", "Motorola"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1051&q=xiaomi", "Xiaomi"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1000&q=smartwatch", "Smartwatch"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1000&q=fone+bluetooth", "Fones"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1000&q=caixa+de+som+bluetooth", "Caixas de Som"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1066&q=smart+tv+55", "Smart TV 55"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1066&q=smart+tv+65", "Smart TV 65"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1039&q=controle+gamer", "Controles"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1002&q=soundbar", "Soundbar"),
]


def buscar_profundo():
    """Busca profunda ML via ScrapingAnt."""
    log("ML BUSCA PROFUNDA iniciada...")

    if not SCRAPINGANT_KEY and not ZENROWS_KEY and not SCRAPERAPI_KEY:
        log("ML profundo: nenhuma chave de scraping configurada")
        return []
    todos = []
    vistos = set()
    total_bruto = 0

    # Usa TODAS as URLs (normais + extras) em vez de amostra de 4
    todas_urls = URLS_BUSCA + URLS_BUSCA_EXTRA

    for url, nome in todas_urls:
        try:
            log(f"ML profundo buscando: {nome}")
            html = scraper_fetch(url)
            items = extrair_produtos_html(html)
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
            log(f"ML profundo erro {nome}: {e}")
            continue

    log(f"ML BUSCA PROFUNDA: {total_bruto} brutos → {len(todos)} válidos")
    return todos
