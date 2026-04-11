"""
Mercado Livre Affiliates — via SerpApi Google Shopping
Publisher ID: ot20260326074822
Busca produtos do ML com desconto real via Google Shopping
"""

import os
import re
import random
import hashlib
import time
import requests

ML_PUBLISHER_ID = os.getenv("ML_PUBLISHER_ID", "ot20260326074822")
SERPAPI_KEY     = os.getenv("SERPAPI_KEY", "")

PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

KEYWORDS = [
    # Monitores
    "monitor gamer 144hz mercado livre",
    "monitor gamer 165hz mercado livre",
    "monitor gamer 240hz mercado livre",
    "monitor 4k mercado livre",
    "monitor curvo mercado livre",
    "monitor ultrawide mercado livre",
    "monitor led full hd mercado livre",
    "monitor 27 polegadas mercado livre",
    "monitor 24 polegadas mercado livre",
    # TVs
    "smart tv 4k mercado livre",
    "tv qled mercado livre",
    "tv oled mercado livre",
    "smart tv 55 polegadas mercado livre",
    "smart tv 50 polegadas mercado livre",
    "smart tv samsung mercado livre",
    "smart tv lg mercado livre",
    "tv led mercado livre",
    # Video Games e Consoles
    "playstation 5 mercado livre",
    "xbox series x mercado livre",
    "nintendo switch mercado livre",
    "controle ps5 mercado livre",
    "controle xbox mercado livre",
    "controle gamer mercado livre",
    "jogo ps5 mercado livre",
    "jogo xbox mercado livre",
    # Periféricos Gamer
    "teclado mecanico mercado livre",
    "teclado gamer rgb mercado livre",
    "mouse gamer mercado livre",
    "mouse sem fio mercado livre",
    "headset gamer mercado livre",
    "cadeira gamer mercado livre",
    # Componentes de PC
    "ssd nvme mercado livre",
    "ssd 1tb mercado livre",
    "memoria ram ddr4 mercado livre",
    "memoria ram ddr5 mercado livre",
    "placa de video mercado livre",
    "processador intel mercado livre",
    "processador amd ryzen mercado livre",
    "fonte pc 650w mercado livre",
    "fonte pc modular mercado livre",
    "placa mae mercado livre",
    "cooler cpu mercado livre",
    "gabinete gamer mercado livre",
    # Notebooks
    "notebook gamer mercado livre",
    "notebook samsung mercado livre",
    "notebook dell mercado livre",
    "notebook lenovo mercado livre",
    # Smartphones
    "smartphone samsung mercado livre",
    "iphone mercado livre",
    "xiaomi redmi mercado livre",
    "motorola edge mercado livre",
    "smartphone 5g mercado livre",
    # Áudio e Acessórios
    "fone bluetooth mercado livre",
    "caixa de som bluetooth mercado livre",
    "smartwatch mercado livre",
    "robo aspirador mercado livre",
    "airfryer mercado livre",
    "webcam full hd mercado livre",
    "power bank mercado livre",
]

PALAVRAS_BLOQUEADAS = [
    "bola de futebol", "bola gigante", "bola pvc", "bola praia",
    "brinquedo", "brinquedos", "jogos ao ar livre", "esporte ao ar livre",
    "football net", "soccer net", "goal net", "rede de futebol",
    "boxing glove", "luva de boxe", "yoga mat", "haltere", "dumbbell",
    "bicicleta", "bike", "skate", "patins", "raquete",
    "roupa", "roupas", "vestido", "camisa", "camiseta", "calca",
    "sapato", "sandalia", "bolsa", "carteira", "chapeu",
    "peruca", "extensao cabelo",
    "furadeira", "parafusadeira", "martelo", "serra",
    "multimetro", "clamp meter",
    "churrasqueira", "fogueira", "grelha", "espeto",
    "cortador de grama", "vaso de planta", "mangueira jardim",
    "suplemento", "creatina", "whey protein", "vitamina",
    "remedio", "medicamento", "farmacia",
]


def produto_valido(nome):
    nome_lower = nome.lower()
    for palavra in PALAVRAS_BLOQUEADAS:
        if palavra in nome_lower:
            return False
    return True


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


def gerar_link_afiliado(url_produto):
    if "mercadolivre.com.br" not in url_produto:
        return url_produto
    separador = "&" if "?" in url_produto else "?"
    return f"{url_produto}{separador}matt_tool={ML_PUBLISHER_ID}"


def extrair_preco_num(preco_str):
    if not preco_str:
        return 0.0
    try:
        limpo = re.sub(r'[^\d,.]', '', str(preco_str))
        limpo = limpo.replace('.', '').replace(',', '.')
        return float(limpo)
    except:
        return 0.0


def buscar_keyword_serpapi(keyword, limit=10):
    if not SERPAPI_KEY:
        return []
    try:
        params = {
            "engine":  "google_shopping",
            "q":       keyword,
            "gl":      "br",
            "hl":      "pt",
            "num":     limit,
            "api_key": SERPAPI_KEY,
        }
        r = requests.get("https://serpapi.com/search", params=params, timeout=20)
        if r.status_code != 200:
            print(f"ML SerpApi erro {r.status_code}")
            return []
        data = r.json()
        items = data.get("shopping_results", [])
        total = len(items)

        # Debug — mostra fontes e links dos primeiros resultados
        if items:
            for i in items[:2]:
                print(f"  SerpApi item: source={i.get('source','?')} link={i.get('link','')[:60]}")

        # Filtra pelo ML — link direto ou source
        ml_items = [i for i in items if
                    "mercadolivre.com.br" in i.get("link", "") or
                    "mercado livre" in i.get("source", "").lower() or
                    "mercadolivre" in i.get("source", "").lower()]

        print(f"  SerpApi '{keyword[:35]}': {total} resultados → {len(ml_items)} do ML")
        return ml_items
    except Exception as e:
        print(f"ML SerpApi keyword '{keyword}' erro: {e}")
        return []


def processar_item_serp(item):
    try:
        # Debug — loga campos do primeiro item para diagnóstico
        if not hasattr(processar_item_serp, '_debug_logged'):
            processar_item_serp._debug_logged = True
            print(f"  ML debug keys: {list(item.keys())}")
            print(f"  ML debug: price={item.get('price')} extracted={item.get('extracted_price')} link={str(item.get('link',''))[:60]} product_link={str(item.get('product_link',''))[:60]}")

        nome = item.get("title", "").strip()
        if not nome or not produto_valido(nome):
            return None

        # Tenta todos os campos de link disponíveis
        link_ml = (item.get("product_link") or
                   item.get("link") or
                   item.get("url") or "")

        # Se não tiver link direto do ML, tenta montar via product_id
        if not link_ml or "mercadolivre.com.br" not in link_ml:
            product_id = item.get("product_id", "")
            if product_id:
                link_ml = f"https://www.mercadolivre.com.br/p/{product_id}"
            else:
                return None

        # Tenta preço em vários campos
        preco = extrair_preco_num(str(item.get("price", "") or
                                      item.get("extracted_price", "") or ""))
        if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None

        # Tenta pegar preço original se disponível (não obrigatório)
        preco_orig = 0.0
        desconto = 0
        for campo in ["old_price", "original_price"]:
            val = item.get(campo)
            if val:
                preco_orig = extrair_preco_num(str(val))
                if preco_orig > preco:
                    desconto = int((1 - preco / preco_orig) * 100)
                    break
                else:
                    preco_orig = 0.0

        imagem = item.get("thumbnail", "")
        link_afiliado = gerar_link_afiliado(link_ml)
        link_curto    = encurtar_link(link_afiliado)

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
        print(f"ML processar item erro: {e}")
        return None


def buscar_todos_produtos():
    todos       = []
    vistos      = set()
    total_bruto = 0

    if not SERPAPI_KEY:
        print("ML SerpApi: SERPAPI_KEY nao configurada — pulando busca ML")
        return []

    keywords_shuffle = random.sample(KEYWORDS, min(10, len(KEYWORDS)))

    for keyword in keywords_shuffle:
        try:
            items = buscar_keyword_serpapi(keyword, limit=10)
            total_bruto += len(items)
            for item in items:
                p = processar_item_serp(item)
                if p:
                    chave = hashlib.md5(p["nome"].encode()).hexdigest()
                    if chave not in vistos:
                        vistos.add(chave)
                        todos.append(p)
            time.sleep(2)
        except Exception as e:
            print(f"ML keyword '{keyword}' erro: {e}")
            continue

    print(f"Mercado Livre (SerpApi): {total_bruto} itens ML → {len(todos)} produtos válidos")
    return todos
