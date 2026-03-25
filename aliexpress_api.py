"""
AliExpress Affiliates API — integração oficial
AppKey: 530504
"""

import hashlib
import time
import requests

ALIEXPRESS_APP_KEY    = "530504"
ALIEXPRESS_APP_SECRET = "ubsjVAWmokbBynXv0uYsQz2PJSwsshXP"
ALIEXPRESS_TRACKING   = "default"

CATEGORIAS = [
    "smartwatch fitness tracker",
    "wireless earbuds noise cancelling",
    "mechanical keyboard gaming",
    "gaming mouse wireless",
    "mini projector portable",
    "robot vacuum cleaner wifi",
    "air fryer electric",
    "power bank 20000mah fast charge",
    "security camera wifi outdoor",
    "smart led strip lights",
    "bluetooth speaker waterproof",
    "laptop stand adjustable",
    "webcam 1080p streaming",
    "electric toothbrush sonic",
    "dash cam car recorder",
    "gadget smart home",
    "gadget kitchen electric",
    "gadget office desk",
    "cool gadget men",
    "tech gadget 2025",
]

PRECO_MINIMO    = 30.00
PRECO_MAXIMO    = 300.00
DESCONTO_MINIMO = 20


def gerar_assinatura(params, secret):
    """
    Assinatura MD5 no formato correto do AliExpress Open API:
    secret + chave1valor1chave2valor2... + secret (ordenado alfabeticamente)
    """
    keys = sorted(params.keys())
    base = secret + "".join(f"{k}{params[k]}" for k in keys) + secret
    return hashlib.md5(base.encode("utf-8")).hexdigest().upper()


def buscar_produtos_aliexpress(keyword, limit=10):
    """Busca produtos por keyword usando a API de afiliados."""
    try:
        timestamp = str(int(time.time() * 1000))

        params = {
            "app_key":         ALIEXPRESS_APP_KEY,
            "timestamp":       timestamp,
            "sign_method":     "md5",
            "method":          "aliexpress.affiliate.product.query",
            "keywords":        keyword,
            "page_no":         "1",
            "page_size":       str(limit),
            "sort":            "SALE_PRICE_ASC",
            "target_currency": "BRL",
            "target_language": "PT",
            "tracking_id":     ALIEXPRESS_TRACKING,
            "ship_to_country": "BR",
            "fields":          "product_id,product_title,target_sale_price,target_original_price,target_sale_price_currency,discount,evaluate_rate,lastest_volume,product_main_image_url,promotion_link",
        }

        params["sign"] = gerar_assinatura(params, ALIEXPRESS_APP_SECRET)

        url = "https://api-sg.aliexpress.com/sync"
        r = requests.post(url, data=params, timeout=15)

        if r.status_code != 200:
            print(f"AliExpress HTTP erro: {r.status_code}")
            return []

        data = r.json()
        resp = data.get("aliexpress_affiliate_product_query_response", {})
        result = resp.get("resp_result", {})

        if result.get("resp_code") != 200:
            print(f"AliExpress API erro: {result.get('resp_msg')}")
            return []

        items = result.get("result", {}).get("products", {}).get("product", [])
        produtos = []

        for item in items:
            try:
                preco = float(str(item.get("target_sale_price", "0")).replace(",", "."))
                preco_orig = float(str(item.get("target_original_price", "0")).replace(",", "."))
            except:
                continue

            if preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
                continue

            desconto = 0
            if preco_orig > preco:
                desconto = int((1 - preco / preco_orig) * 100)

            if desconto < DESCONTO_MINIMO:
                continue

            nome = item.get("product_title", "")
            link = item.get("promotion_link", "")
            imagem = item.get("product_main_image_url", "")

            if not nome or not link:
                continue

            produtos.append({
                "nome": nome,
                "preco": round(preco, 2),
                "preco_original": round(preco_orig, 2),
                "desconto": desconto,
                "loja": "ALIEXPRESS",
                "frete": "🚢 Frete grátis",
                "link_afiliado": link,
                "imagem_url": imagem,
                "score": 1,
                "fontes": ["aliexpress"],
            })

        return produtos

    except Exception as e:
        print(f"AliExpress erro ({keyword}): {e}")
        return []


def buscar_todos_produtos():
    """Busca produtos em todas as categorias."""
    import hashlib as _h

    todos = []
    vistos = set()

    for keyword in CATEGORIAS:
        try:
            produtos = buscar_produtos_aliexpress(keyword, limit=5)
            for p in produtos:
                chave = _h.md5(p["nome"].encode()).hexdigest()
                if chave not in vistos:
                    vistos.add(chave)
                    todos.append(p)
            time.sleep(1)
        except Exception as e:
            print(f"Erro em {keyword}: {e}")
            continue

    print(f"AliExpress API: {len(todos)} produtos encontrados")
    return todos
