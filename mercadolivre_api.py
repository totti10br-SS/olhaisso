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
    "monitor gamer mercado livre",
    "monitor 4k mercado livre",
    "notebook gamer mercado livre",
    "processador intel mercado livre",
    "processador amd ryzen mercado livre",
    "ssd nvme mercado livre",
    "memoria ram ddr4 mercado livre",
    "placa de video mercado livre",
    "smartphone samsung mercado livre",
    "iphone mercado livre",
    "xiaomi redmi mercado livre",
    "motorola edge mercado livre",
    "fone bluetooth mercado livre",
    "headset gamer mercado livre",
    "teclado mecanico mercado livre",
    "mouse gamer mercado livre",
    "smart tv 4k mercado livre",
    "playstation 5 mercado livre",
    "xbox series mercado livre",
    "nintendo switch mercado livre",
    "robo aspirador mercado livre",
    "airfryer mercado livre",
    "caixa de som bluetooth mercado livre",
    "smartwatch mercado livre",
    "power bank mercado livre",
    "webcam full hd mercado livre",
    "controle gamer mercado livre",
    "tv oled mercado livre",
    "tv qled mercado livre",
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
        items = r.json().get("shopping_results", [])
        return [i for i in items if "mercadolivre.com.br" in i.get("link", "")]
    except Exception as e:
        print(f"ML SerpApi keyword '{keyword}' erro: {e}")
        return []


def processar_item_serp(item):
    try:
        nome = item.get("title", "").strip()
        if not nome or not produto_valido(nome):
            return None

        link_ml = item.get("link", "")
        if "mercadolivre.com.br" not in link_ml:
            return None

        preco = extrair_preco_num(str(item.get("price", "") or ""))
        if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None

        # Preco original — so aceita se vier real
        preco_orig = 0.0
        for campo in ["old_price", "extracted_price", "original_price"]:
            val = item.get(campo)
            if val:
                preco_orig = extrair_preco_num(str(val))
                if preco_orig > preco:
                    break
                else:
                    preco_orig = 0.0

        desconto = 0
        if preco_orig > preco > 0:
            desconto = int((1 - preco / preco_orig) * 100)

        if desconto < DESCONTO_MINIMO:
            return None

        imagem = item.get("thumbnail", "")
        link_afiliado = gerar_link_afiliado(link_ml)
        link_curto    = encurtar_link(link_afiliado)

        return {
            "nome":           nome,
            "preco":          round(preco, 2),
            "preco_original": round(preco_orig, 2),
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

    print(f"Mercado Livre (SerpApi): {total_bruto} itens ML → {len(todos)} com desconto real >= {DESCONTO_MINIMO}%")
    return todos
