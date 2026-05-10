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
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1648", "Computação"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1051", "Celulares"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1000", "Eletrônicos"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1066", "TVs"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1039", "Video Games"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1002", "Áudio"),
    ("https://www.mercadolivre.com.br/ofertas?category=MLB1648&q=gabinete%20gamer", "Gabinetes para PC"),
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


def encurtar_link(url_longa):
    try:
        r = requests.get(f"https://tinyurl.com/api-create.php?url={url_longa}", timeout=5)
        if r.status_code == 200 and r.text.startswith("https://"):
            return r.text.strip()
    except:
        pass
    return url_longa


def scraper_fetch(url):
    # ScrapingAnt
    if SCRAPINGANT_KEY:
        try:
            params = {
                "url":           url,
                "x-api-key":     SCRAPINGANT_KEY,
                "proxy_country": "BR",
                "browser":       "false",
            }
            r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=60)
            log(f"  ScrapingAnt {r.status_code} → {url[:60]}")
            if r.status_code == 200:
                return r.text
            log(f"  ScrapingAnt erro: {r.text[:100]}")
        except Exception as e:
            log(f"  ScrapingAnt erro: {e}")

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


def buscar_todos_produtos():
    if not SCRAPINGANT_KEY and not ZENROWS_KEY and not SCRAPERAPI_KEY:
        log("ML: nenhuma chave de scraping configurada")
        return []

    log("ML ScrapingAnt: iniciando busca...")
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

    log(f"Mercado Livre (ScrapingAnt): {total_bruto} brutos → {len(todos)} válidos")
    return todos
