"""
AliExpress Affiliates API — integração oficial
AppKey: 530504
"""

import os
import hashlib
import time
import requests

ALIEXPRESS_APP_KEY    = "530504"
ALIEXPRESS_APP_SECRET = "ubsjVAWmokbBynXv0uYsQz2PJSwsshXP"
ALIEXPRESS_TRACKING   = "default"

CATEGORIAS = [
    # Periféricos gamer — top Brasil 2025
    "mechanical keyboard hot swappable",
    "gaming controller hall effect",
    "gaming mouse rgb wireless",
    "gaming headset surround",
    # Áudio e mobile
    "wireless earbuds noise cancelling anc",
    "smartwatch health monitor",
    "power bank magnetic fast charge",
    "bluetooth speaker portable",
    "dash cam 4k car",
    # Casa inteligente
    "robot vacuum mop wifi",
    "smart led strip rgb",
    "air fryer digital",
    "mini projector portable 1080p",
    # Câmera — apenas uma keyword
    "security camera wifi outdoor",
    # Informática e upgrade
    "ssd portable external",
    "usb hub docking station",
    "webcam streaming 1080p",
    "laptop cooling stand",
    "electric desk lamp led",
    # Monitores — prioridade alta
    "gaming monitor 144hz",
    "gaming monitor 165hz",
    "gaming monitor 240hz",
    "monitor 4k ips",
    "monitor ultrawide curved",
    "portable monitor usb-c",
    "monitor 27 inch 1440p",
    "monitor 24 inch full hd",
    "monitor 144hz 1ms",
    "monitor 2k gaming",
    # Gadgets direcionados
    "gadget smart home 2025",
    "cool gadget men gift",
    "gadget kitchen electric",
    "neck fan hands free",
    "gadget office productivity",
    # Virais
    "viral gadget tiktok 2025",
    "trending gadget 2025",
    "viral product tiktok bought",
    "gadget viral instagram",
    "best selling gadget 2025",
    "tiktok made me buy gadget",
    "viral tech product",
    "gadget that went viral",
    # Copa do Mundo 2026
    "world cup 2026 gadget",
    "soccer fan gadget",
    "football led fan",
    "sports bluetooth speaker",
    "mini projector football",
    "led jersey light fan",
    "stadium fan accessories",
    "world cup smart watch",
    # Marcas premium
    "xiaomi earbuds",
    "xiaomi smartwatch band",
    "baseus charger fast",
    "baseus power bank",
    "anker charger gan",
    "anker power bank",
    "jbl speaker bluetooth",
    "jbl earbuds",
    "redragon gaming mouse",
    "redragon keyboard",
    "logitech mouse wireless",
    "logitech keyboard",
    "samsung ssd portable",
    "philips smart lamp",
]

PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "800.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

# Preços em USD para filtro na API (R$50=~$9 / R$800=~$145)
PRECO_MIN_USD = "9"
PRECO_MAX_USD = "145"

# Palavras que indicam produto técnico, fora do nicho ou indesejado
PALAVRAS_BLOQUEADAS = [
    # Termos técnicos em português
    "separador de tela", "manutenção", "desmontagem", "reparo", "solda",
    "placa mãe", "cabo flex", "ferramenta de", "kit de reparo",
    "separador lcd", "aquecimento para", "abertura de celular",
    "substituição", "peça de reposição", "conserto",
    "chave de fenda", "alicate", "pinça", "estação de solda",
    # Manutenção e reparo técnico
    "repair", "maintenance", "soldering", "pcb", "lcd separator",
    "rework", "fixture", "jig", "spare part", "replacement part",
    "motherboard", "flex cable", "digitizer", "screen separator",
    # Atacado / industrial
    "wholesale", "bulk", "lot of", "pcs lot", "oem", "odm",
    "industrial", "factory", "mold", "tool kit professional",
    # Fora do nicho
    "wig", "hair extension", "nail art", "eyelash", "lace front",
    "fishing", "hunting", "bait", "hook",
    "medical", "surgical", "clinical", "dental",
    "diaper", "baby formula", "pet food",
]


def produto_valido(nome):
    """Verifica se o produto não contém palavras bloqueadas."""
    nome_lower = nome.lower()
    for palavra in PALAVRAS_BLOQUEADAS:
        if palavra in nome_lower:
            return False
    return True


def encurtar_link(url_longa):
    """Encurta link usando TinyURL — gratuito, sem API key."""
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


def gerar_assinatura(params, secret):
    keys = sorted(params.keys())
    base = secret + "".join(f"{k}{params[k]}" for k in keys) + secret
    return hashlib.md5(base.encode("utf-8")).hexdigest().upper()


def buscar_produtos_aliexpress(keyword, limit=10):
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
            "sort":            "LAST_VOLUME_DESC",
            "min_sale_price":  PRECO_MIN_USD,
            "max_sale_price":  PRECO_MAX_USD,
            "target_currency": "BRL",
            "target_language": "PT",
            "tracking_id":     ALIEXPRESS_TRACKING,
            "ship_to_country": "BR",
            "fields":          "product_id,product_title,target_sale_price,target_original_price,target_sale_price_currency,discount,evaluate_rate,lastest_volume,product_main_image_url,promotion_link",
        }
        params["sign"] = gerar_assinatura(params, ALIEXPRESS_APP_SECRET)

        r = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15)
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
            link_original = item.get("promotion_link", "")
            imagem = item.get("product_main_image_url", "")

            if not nome or not link_original:
                continue

            # Filtra produtos fora do nicho
            if not produto_valido(nome):
                print(f"  Bloqueado: {nome[:50]}")
                continue

            link = encurtar_link(link_original)

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
