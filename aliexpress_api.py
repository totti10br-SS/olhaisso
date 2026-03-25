"""
AliExpress Affiliates API — integração oficial
AppKey: 530504
"""

import hashlib
import hmac
import time
import requests

ALIEXPRESS_APP_KEY    = "530504"
ALIEXPRESS_APP_SECRET = "ubsjVAWmokbBynXv0uYsQz2PJSwsshXP"
ALIEXPRESS_TRACKING   = "olhaissotech"

CATEGORIAS = [
    "bluetooth earphone",
    "smart watch",
    "usb charger gan",
    "wireless mouse keyboard",
    "led lamp smart home",
    "mini projector",
    "power bank",
    "webcam",
    "robot vacuum",
    "air fryer",
    "phone holder",
    "usb hub",
]

PRECO_MAXIMO    = 300.00
DESCONTO_MINIMO = 20


def gerar_assinatura(params, secret):
    """Gera assinatura HMAC-MD5 para API do AliExpress."""
    keys = sorted(params.keys())
    base = secret + "".join(f"{k}{params[k]}" for k in keys) + secret
    return hmac.new(secret.encode(), base.encode(), hashlib.md5).hexdigest().upper()


def chamar_api(method, params_extras={}):
    """Chama endpoint da AliExpress Open API."""
    url = "https://api-sg.aliexpress.com/sync"
    params = {
        "app_key": ALIEXPRESS_APP_KEY,
        "timestamp": str(int(time.time() * 1000)),
        "sign_method": "hmac",
        "method": method,
        **params_extras,
    }
    params["sign"] = gerar_assinatura(params, ALIEXPRESS_APP_SECRET)
    try:
        r = requests.post(url, data=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"AliExpress API erro: {e}")
    return {}


def buscar_produtos_aliexpress(keyword, limit=10):
    """Busca produtos por keyword usando a API de afiliados."""
    resp = chamar_api("aliexpress.affiliate.product.query", {
        "keywords": keyword,
        "page_no": "1",
        "page_size": str(limit),
        "sort": "SALE_PRICE_ASC",
        "target_currency": "BRL",
        "target_language": "PT",
        "tracking_id": ALIEXPRESS_TRACKING,
        "ship_to_country": "BR",
    })

    produtos = []
    try:
        items = (
            resp.get("aliexpress_affiliate_product_query_response", {})
                .get("resp_result", {})
                .get("result", {})
                .get("products", {})
                .get("product", [])
        )

        for item in items:
            preco_str = item.get("target_sale_price", "0")
            preco_orig_str = item.get("target_original_price", "0")

            try:
                preco = float(str(preco_str).replace(",", "."))
                preco_orig = float(str(preco_orig_str).replace(",", "."))
            except:
                continue

            if preco <= 0 or preco > PRECO_MAXIMO:
                continue

            desconto = 0
            if preco_orig > preco:
                desconto = int((1 - preco / preco_orig) * 100)

            if desconto < DESCONTO_MINIMO:
                continue

            nome = item.get("product_title", "")
            link = item.get("promotion_link", item.get("product_detail_url", ""))
            imagem = item.get("product_main_image_url", "")
            vendas = item.get("lastest_volume", 0)
            avaliacao = float(item.get("evaluate_rate", "0%").replace("%", "") or 0)

            produtos.append({
                "nome": nome,
                "preco": round(preco, 2),
                "preco_original": round(preco_orig, 2),
                "desconto": desconto,
                "loja": "ALIEXPRESS",
                "frete": "🚢 Frete grátis",
                "link_afiliado": link,
                "imagem_url": imagem,
                "vendas": vendas,
                "avaliacao": avaliacao,
                "score": 1,
                "fontes": ["aliexpress"],
            })

    except Exception as e:
        print(f"AliExpress parse erro: {e}")

    return produtos


def buscar_todos_produtos():
    """Busca produtos em todas as categorias."""
    todos = []
    vistos = set()

    for keyword in CATEGORIAS:
        try:
            produtos = buscar_produtos_aliexpress(keyword, limit=5)
            for p in produtos:
                chave = hashlib.md5(p["nome"].encode()).hexdigest()
                if chave not in vistos:
                    vistos.add(chave)
                    todos.append(p)
            time.sleep(1)
        except Exception as e:
            print(f"Erro em {keyword}: {e}")
            continue

    print(f"AliExpress API: {len(todos)} produtos encontrados")
    return todos


if __name__ == "__main__":
    print("Testando AliExpress API...")
    produtos = buscar_todos_produtos()
    for p in produtos[:5]:
        print(f"\n{p['nome'][:60]}")
        print(f"  Preço: R$ {p['preco']:.2f} (era R$ {p['preco_original']:.2f})")
        print(f"  Desconto: {p['desconto']}%")
        print(f"  Link: {p['link_afiliado'][:60]}...")
