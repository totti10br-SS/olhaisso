"""
Integração Shopee Afiliados — sem API oficial
Usa scraping público da Shopee + geração de link rastreado
ID Afiliado: 18307831002
Username: olhaissotech
"""

import requests
import hashlib
import time
import json
from urllib.parse import quote

SHOPEE_AFFILIATE_ID = "18307831002"
SHOPEE_USERNAME     = "olhaissotech"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://shopee.com.br/",
}

CATEGORIAS_GADGET = [
    "fone bluetooth",
    "carregador gan",
    "smartwatch",
    "teclado gamer",
    "mouse sem fio",
    "caixa de som bluetooth",
    "webcam full hd",
    "hub usb",
    "power bank",
    "luminaria led",
    "projetor mini",
    "aspirador portatil",
    "fritadeira airfryer",
    "tomada inteligente",
    "cabo usb c",
]

PRECO_MAXIMO    = 300.00
DESCONTO_MINIMO = 20


def gerar_link_afiliado(url_produto):
    """
    Converte URL de produto Shopee em link rastreado de afiliado.
    Usa o endpoint público da Shopee Afiliados.
    """
    try:
        endpoint = "https://affiliate.shopee.com.br/api/v2/links/generate"
        payload = {
            "originUrl": url_produto,
            "subId": SHOPEE_USERNAME,
        }
        headers = {
            **HEADERS,
            "Content-Type": "application/json",
        }
        r = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            link = data.get("data", {}).get("generateLink", "")
            if link:
                return link

        # Fallback: formato padrão de link de afiliado Shopee
        encoded = quote(url_produto, safe="")
        return f"https://s.shopee.com.br/affiliate?pid={SHOPEE_AFFILIATE_ID}&url={encoded}"

    except Exception as e:
        # Fallback simples
        return url_produto


def buscar_produtos_shopee(keyword, limit=5):
    """
    Busca produtos na Shopee por palavra-chave.
    Retorna lista de produtos com nome, preço, desconto e URL.
    """
    try:
        url = "https://shopee.com.br/api/v4/search/search_items"
        params = {
            "by": "relevancy",
            "keyword": keyword,
            "limit": limit,
            "newest": 0,
            "order": "desc",
            "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH",
            "version": 2,
            "price_min": 1000,       # em centavos = R$10
            "price_max": 30000000,   # em centavos = R$300
        }

        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []

        items = r.json().get("items", []) or []
        produtos = []

        for item in items:
            info = item.get("item_basic", {})

            nome = info.get("name", "")
            preco_raw = info.get("price", 0)
            preco_orig_raw = info.get("price_before_discount", 0)
            preco = preco_raw / 100000
            preco_orig = preco_orig_raw / 100000 if preco_orig_raw > 0 else preco * 1.3
            desconto = info.get("discount", 0)
            shop_id = info.get("shopid", "")
            item_id = info.get("itemid", "")
            imagem = info.get("image", "")
            rating = info.get("item_rating", {}).get("rating_star", 0)
            vendas = info.get("sold", 0)

            if preco <= 0 or preco > PRECO_MAXIMO:
                continue
            if desconto < DESCONTO_MINIMO:
                continue
            if rating < 4.0:
                continue

            # Monta URL do produto
            nome_url = nome.lower().replace(" ", "-")[:50]
            url_produto = f"https://shopee.com.br/{nome_url}-i.{shop_id}.{item_id}"

            # Gera link de afiliado
            link_afiliado = gerar_link_afiliado(url_produto)

            # URL da imagem
            img_url = f"https://cf.shopee.com.br/file/{imagem}" if imagem else ""

            produtos.append({
                "nome": nome,
                "preco": round(preco, 2),
                "preco_original": round(preco_orig, 2),
                "desconto": desconto,
                "loja": "SHOPEE",
                "frete": "✅ Frete grátis",
                "link_afiliado": link_afiliado,
                "imagem_url": img_url,
                "rating": rating,
                "vendas": vendas,
                "score": 1,
                "fontes": ["shopee"],
            })

        return produtos

    except Exception as e:
        print(f"Shopee scraping erro ({keyword}): {e}")
        return []


def buscar_todos_gadgets():
    """
    Busca produtos em todas as categorias do nicho.
    Retorna lista consolidada sem duplicatas.
    """
    todos = []
    vistos = set()

    for keyword in CATEGORIAS_GADGET:
        try:
            produtos = buscar_produtos_shopee(keyword, limit=3)
            for p in produtos:
                chave = hashlib.md5(p["nome"].encode()).hexdigest()
                if chave not in vistos:
                    vistos.add(chave)
                    todos.append(p)
            time.sleep(1.5)
        except Exception as e:
            print(f"Erro em {keyword}: {e}")
            continue

    print(f"Shopee scraping: {len(todos)} produtos únicos encontrados")
    return todos


if __name__ == "__main__":
    print("Testando busca Shopee...")
    produtos = buscar_todos_gadgets()
    for p in produtos[:5]:
        print(f"\n{p['nome'][:50]}")
        print(f"  Preço: R$ {p['preco']:.2f} (era R$ {p['preco_original']:.2f})")
        print(f"  Desconto: {p['desconto']}%")
        print(f"  Link: {p['link_afiliado'][:60]}...")
