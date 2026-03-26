"""
Shopee Affiliates API — integração oficial
AppID: 18307831002
Assinatura: SHA256(AppId + Timestamp + Payload + Secret)
"""

import hashlib
import time
import json
import requests

SHOPEE_APP_ID = "18307831002"
SHOPEE_SECRET = "5TCZ4KND77VOJV5QNUX7PMYKTVPF23XT"
SHOPEE_URL    = "https://open-api.affiliate.shopee.com.br/graphql"

CATEGORIAS = [
    "fone bluetooth",
    "smartwatch",
    "carregador gan",
    "teclado gamer",
    "mouse sem fio",
    "caixa de som bluetooth",
    "power bank",
    "webcam full hd",
    "hub usb",
    "projetor mini",
    "aspirador portatil",
    "fritadeira airfryer",
    "tomada inteligente",
    "luminaria led",
    "camera seguranca wifi",
    "fita led rgb",
    "headset gamer",
    "suporte notebook",
    "relogio inteligente",
    "controle gamer",
]

PRECO_MINIMO    = 50.00
PRECO_MAXIMO    = 800.00
DESCONTO_MINIMO = 20

PALAVRAS_BLOQUEADAS = [
    "separador de tela", "manutenção", "desmontagem", "reparo", "solda",
    "placa mãe", "cabo flex", "ferramenta de", "kit de reparo",
    "separador lcd", "substituição", "peça de reposição", "conserto",
    "chave de fenda", "alicate", "pinça", "estação de solda",
    "repair", "maintenance", "soldering", "pcb", "lcd separator",
    "rework", "fixture", "jig", "spare part", "replacement part",
    "motherboard", "flex cable", "digitizer", "screen separator",
    "wholesale", "bulk", "lot of", "pcs lot", "oem", "odm",
    "wig", "hair extension", "nail art", "eyelash",
    "fishing", "hunting", "medical", "surgical", "dental",
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


def gerar_assinatura(app_id, timestamp, payload_str, secret):
    """Assinatura correta: SHA256(AppId + Timestamp + Payload + Secret)"""
    fator = app_id + str(timestamp) + payload_str + secret
    return hashlib.sha256(fator.encode("utf-8")).hexdigest()


def buscar_produtos_shopee(keyword, limit=10):
    """Busca produtos via Shopee Affiliate API GraphQL."""
    try:
        query = """query getProducts($keyword: String!, $limit: Int!, $page: Int!) {
  productOfferV2(
    listType: 0,
    sortType: 2,
    keyword: $keyword,
    limit: $limit,
    page: $page
  ) {
    nodes {
      productName
      priceMin
      priceMax
      priceDiscountRate
      imageUrl
      offerLink
      productLink
      commissionRate
    }
    pageInfo { hasNextPage }
  }
}"""

        variables = {"keyword": keyword, "limit": limit, "page": 1}
        body = {
            "query": query,
            "operationName": "getProducts",
            "variables": variables
        }

        # Payload como string compacta para assinatura
        payload_str = json.dumps(body, separators=(",", ":"))
        timestamp = int(time.time())
        sign = gerar_assinatura(SHOPEE_APP_ID, timestamp, payload_str, SHOPEE_SECRET)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={SHOPEE_APP_ID},Timestamp={timestamp},Signature={sign}",
        }

        r = requests.post(SHOPEE_URL, data=payload_str, headers=headers, timeout=15)

        if r.status_code != 200:
            print(f"Shopee HTTP erro {r.status_code}: {r.text[:200]}")
            return []

        data = r.json()

        # Verifica erros GraphQL
        if "errors" in data:
            print(f"Shopee GraphQL erro: {data['errors']}")
            return []

        nodes = data.get("data", {}).get("productOfferV2", {}).get("nodes", []) or []
        produtos = []

        for item in nodes:
            try:
                preco = float(str(item.get("priceMin", "0")).replace(",", "."))
                desc_raw = item.get("priceDiscountRate", "0") or "0"
                desconto = int(str(desc_raw).replace("%", "").strip() or 0)
            except:
                continue

            if preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
                continue
            if desconto < DESCONTO_MINIMO:
                continue

            nome = item.get("productName", "")
            link_original = item.get("offerLink") or item.get("productLink", "")
            imagem = item.get("imageUrl", "")

            if not nome or not link_original:
                continue

            if not produto_valido(nome):
                print(f"  Shopee bloqueado: {nome[:50]}")
                continue

            preco_orig = round(preco / (1 - desconto / 100), 2) if desconto > 0 else round(preco * 1.3, 2)
            link = encurtar_link(link_original)

            produtos.append({
                "nome": nome,
                "preco": round(preco, 2),
                "preco_original": preco_orig,
                "desconto": desconto,
                "loja": "SHOPEE",
                "frete": "✅ Frete grátis",
                "link_afiliado": link,
                "imagem_url": imagem,
                "score": 1,
                "fontes": ["shopee"],
            })

        return produtos

    except Exception as e:
        print(f"Shopee erro ({keyword}): {e}")
        return []


def buscar_todos_produtos():
    import hashlib as _h
    todos = []
    vistos = set()

    for keyword in CATEGORIAS:
        try:
            produtos = buscar_produtos_shopee(keyword, limit=5)
            for p in produtos:
                chave = _h.md5(p["nome"].encode()).hexdigest()
                if chave not in vistos:
                    vistos.add(chave)
                    todos.append(p)
            time.sleep(1)
        except Exception as e:
            print(f"Erro em {keyword}: {e}")
            continue

    print(f"Shopee API: {len(todos)} produtos encontrados")
    return todos
