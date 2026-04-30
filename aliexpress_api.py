"""
AliExpress Affiliates API — integração oficial
AppKey: 530504
"""

import os
import random
import hashlib
import time
import requests

ALIEXPRESS_APP_KEY    = "530504"
ALIEXPRESS_APP_SECRET = "ubsjVAWmokbBynXv0uYsQz2PJSwsshXP"
ALIEXPRESS_TRACKING   = "default"

CATEGORIAS = [
    # Componentes de PC — PRIORIDADE ALTA
    "ssd nvme m2",
    "ssd nvme 1tb",
    "ssd nvme 512gb",
    "ssd portable external",
    "ssd 1tb interno",
    "ssd 512gb nvme",
    "memoria ram ddr4 16gb",
    "memoria ram ddr4 8gb",
    "memoria ram ddr5",
    "ram 4gb ddr4",
    "ram 8gb ddr4",
    "ram 16gb ddr4",
    "ram 32gb ddr5",
    "ram 8gb ddr5",
    "processador intel core i5",
    "processador intel core i7",
    "processador amd ryzen 5",
    "processador amd ryzen 7",
    "gabinete gamer atx",
    "gabinete gamer rgb",
    "gabinete mid tower",
    "cooler cpu rgb",
    "cooler processador argb",
    "fonte pc modular",
    "fonte atx 650w",
    "fonte atx 750w",
    "placa mae b660",
    "placa mae b550",
    # Periféricos gamer
    "mechanical keyboard hot swappable",
    "gaming keyboard rgb",
    "gaming controller hall effect",
    "gaming mouse rgb wireless",
    "gaming headset surround",
    "teclado gamer rgb",
    "mouse gamer sem fio",
    "headset gamer usb",
    # Monitores
    "gaming monitor 144hz",
    "gaming monitor 165hz",
    "gaming monitor 240hz",
    "monitor 4k ips",
    "monitor curvo gamer",
    "monitor 27 polegadas",
    "monitor 24 polegadas",
    "monitor led full hd",
    "monitor ultrawide",
    "portable monitor usb-c",
    # Áudio e mobile — REDUZIDO
    "wireless earbuds noise cancelling anc",
    "bluetooth speaker portable",
    # Casa inteligente
    "robot vacuum mop wifi",
    "robot vacuum cleaner",
    "smart led strip rgb",
    "air fryer digital",
    "mini projector portable 1080p",
    # Informática
    "usb hub docking station",
    "webcam streaming 1080p",
    "laptop cooling stand",
    "electric desk lamp led",
    # Smartwatch
    "smartwatch health monitor",
    "power bank magnetic fast charge",
    # Gadgets direcionados
    "gadget smart home 2025",
    "cool gadget men gift",
    "neck fan hands free",
    # Virais — tech apenas
    "trending gadget 2025",
    "best selling gadget 2025",
    # Copa do Mundo 2026
    "sports bluetooth speaker",
    "mini projector football",
    "world cup smart watch",
    # Celulares e Smartphones
    "smartphone android",
    "smartphone 5g",
    "xiaomi smartphone",
    "samsung galaxy",
    "motorola smartphone",
    "poco smartphone",
    "redmi smartphone",
    "realme smartphone",
    "smartphone 108mp camera",
    "smartphone gaming",
    # Acessórios de celular
    "capinha celular",
    "carregador celular rapido",
    "cabo usb-c celular",
    "suporte celular carro",
    # Marcas premium
    "xiaomi earbuds",
    "xiaomi smartwatch band",
    "baseus charger fast",
    "baseus power bank",
    "anker charger gan",
    "anker power bank",
    "redragon gaming mouse",
    "redragon keyboard",
    "logitech mouse wireless",
    "logitech keyboard",
    "samsung ssd portable",
]

PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

# Regras exclusivas para ciclo Ticket Baixo — NAO afetam o ciclo normal
TB_PRECO_MINIMO    = float(os.getenv("TB_PRECO_MINIMO", "10.00"))
TB_DESCONTO_MINIMO = int(os.getenv("TB_DESCONTO_MINIMO", "10"))
TB_COTACAO_USD     = float(os.getenv("TB_COTACAO_USD", "5.80"))  # cotacao para converter teto BRL->USD

# Precos em USD para filtro na API (R$50=~$9 / R$3000=~$550)
PRECO_MIN_USD = "9"
PRECO_MAX_USD = "550"

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
    # Eletrônica DIY / fora do nicho
    "arduino", "esp32", "esp8266", "raspberry pi", "diy kit",
    "servo motor", "sensor module", "breadboard", "robot kit",
    "open source robot", "programmable robot", "sg90",
    # Esportes e artigos esportivos fora do nicho
    "football net", "soccer net", "goal net", "training net", "sport net",
    "quarterback", "arremesso", "rede de futebol", "rede esportiva",
    "rede de alvo", "golha de futebol", "gol dobravel", "gol portatil",
    "rede de gol", "trave dobravel", "mini gol", "chute ao gol",
    "chute a gol", "trave de futebol", "gol de futebol",
    "football target", "throwing target", "pitching net",
    "tennis net", "volleyball net", "badminton net",
    "soccer goal", "football goal", "pop up goal",
    "náilon esporte", "nailon futebol", "rede náilon",
    "playground futebol", "quintal futebol", "treinamento futebol",
    "boxing glove", "luva de boxe", "saco de pancada",
    "bicicleta", "bike", "cycling", "ciclismo",
    "skate", "patins", "roller skate",
    "equipamento esportivo", "sport equipment",
    "yoga mat", "tapete yoga", "colchonete",
    "haltere", "dumbbell", "kettlebell", "barbell",
    "elástico musculação", "resistance band",
    "corda de pular", "jump rope",
    "mochila esportiva", "sport backpack",
    "golfe", "golf", "taco de golfe",
    "raquete", "racket", "racquet",
    "capacete bike", "joelheira", "cotoveleira",

    # Brinquedos e esportes ao ar livre — fora do nicho
    "bola de futebol", "bola gigante", "bola pvc", "bola praia",
    "bola verão", "brinquedo", "brinquedos", "toy", "toys",
    "jogos ao ar livre", "jogos esportivos", "esporte ao ar livre",
    "gramado esporte", "queda gramado", "presente jogos",
    "pvc ball", "giant ball", "beach ball", "outdoor game",
    "kite", "pipa", "pião", "bambolê", "frisbee",
    # Ferramentas de medição e elétrica — fora do nicho
    "multímetro", "multimetro", "alicate amperímetro", "alicate amperimetro",
    "medidor de braçadeira", "medidor de bracadeira", "clamp meter",
    "digital clamp", "amperímetro", "amperimetro", "voltímetro", "voltimetro",
    "capacitância", "capacitancia", "medidor de temperatura",
    "testador de cabo", "testador elétrico", "testador eletrico",
    "osciloscópio", "osciloscopio", "analisador de espectro",
    "medidor de energia", "wattímetro", "wattimetro",
    "detector de tensão", "detector de tensao",
    "termômetro infravermelho", "termometro infravermelho",
    # Ferramentas gerais
    "microscopio", "microscópio", "microscopy", "binocular microscope", "optical microscope",
    "telescopio", "telescópio", "estetoscopio", "termometro clinico", "balanca de precisao",
    "furadeira", "parafusadeira", "chave inglesa", "martelo",
    "serra", "esmerilhadeira", "lixadeira",
    "fogueira", "fogão", "fogao", "churrasqueira", "churrasco",
    "fire pit", "campfire", "fireplace", "lareira",
    "suporte para fogueira", "base para fogueira", "queimador",
    "grelha", "espeto", "carvão", "carvaoo", "braseiro",
    "camping stove", "camp fire", "outdoor fire",
    "retrátil ajustável aço inoxidável", "retratil ajustavel",
    "fogão solo", "ranger yukon", "fogueira solo",
    # Jardinagem e ao ar livre
    "cortador de grama", "podadora", "regador",
    "vaso de planta", "adubo", "fertilizante",
    "mangueira jardim", "aspersor",
    "suéter", "sueter", "pulôver", "pulover", "blusa", "blusão",
    "malha", "tricô", "tricot", "knit", "knitwear",
    "algodão macio", "algodao macio", "bordado de urso", "bordado floral",
    "gola redonda", "gola v", "gola alta", "decote v",
    "manga longa", "manga curta", "manga 3/4",
    "top feminino", "top de", "para mulheres", "para homens",
    "feminino", "masculino", "unissex moda",
    "casual confortável", "casual confortavel",
    "blazer", "vestido", "camisa", "camiseta", "blusa", "calça",
    "saia", "shorts", "jaqueta", "casaco", "moletom", "agasalho",
    "roupa", "roupas", "moda", "fashion", "clothing", "dress",
    "shirt", "pants", "jacket", "coat", "sweater", "hoodie",
    "t-shirt", "jeans", "legging", "bermuda", "pijama", "lingerie",
    "sutiã", "calcinha", "cueca", "meia", "sock", "underwear",
    "feminino retrô", "manga longa", "gola alta", "abotoamento",
    "coleção primavera", "coleção verão", "coleção outono",
    "estilo napoleão", "assimétrico", "decote", "tecido",
    "shoe", "sapato", "tênis de moda", "sandália", "chinelo",
    "bolsa", "carteira", "cinto", "chapéu", "boné fashion",
    "óculos de sol", "sunglasses", "acessório moda",
    "peruca", "extensão cabelo", "cabelo", "hair",
]



CATEGORIAS_TICKET_BAIXO = [
    # Periféricos baratos
    "gaming mouse cheap",
    "wireless mouse cheap",
    "gaming keyboard cheap",
    "mechanical keyboard cheap",
    "gaming mousepad rgb",
    "large mousepad desk",
    "gaming headset cheap",
    "bluetooth earbuds cheap",
    "tws earbuds cheap",
    "wireless earphones cheap",
    "webcam 1080p cheap",
    # Setup e acessórios PC baratos
    "usb hub cheap",
    "usb-c cable fast charge",
    "hdmi cable cheap",
    "laptop stand cheap",
    "laptop cooling fan cheap",
    "cpu cooler cheap rgb",
    "led desk lamp cheap",
    "rgb led strip cheap",
    # Acessórios celular
    "phone case cheap",
    "fast charger cheap",
    "usb-c charging cable",
    "car phone holder cheap",
    "ring light selfie",
    "phone screen protector",
    # Armazenamento barato
    "pen drive usb",
    "memory card sd cheap",
    "portable ssd cheap 256gb",
    # Gadgets baratos
    "power bank cheap",
    "bluetooth speaker mini cheap",
    "smart plug wifi cheap",
    "smart bulb cheap",
    "smartwatch cheap",
    "fitness band cheap",
    # Watercooler e cooler barato
    "cpu water cooler cheap",
    "pc case fan rgb cheap",
    "thermal paste cheap",
    # Informática barata
    "monitor stand cheap",
    "desk organizer cheap",
    "bluetooth keyboard tablet",
    "wireless mouse silent",
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
            "page_no":         str(random.randint(1, 3)),
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
    monitor_portatil_count = 0

    for keyword in CATEGORIAS:
        try:
            produtos = buscar_produtos_aliexpress(keyword, limit=5)
            for p in produtos:
                chave = hashlib.md5(p["nome"].encode()).hexdigest()
                if chave not in vistos:
                    nome_lower = p["nome"].lower()
                    eh_portatil = any(kw in nome_lower for kw in ["monitor portátil", "monitor portatil", "portable monitor", "monitor usb-c"])
                    if eh_portatil:
                        if monitor_portatil_count >= 1:
                            continue
                        monitor_portatil_count += 1
                    vistos.add(chave)
                    todos.append(p)
            time.sleep(1)
        except Exception as e:
            print(f"Erro em {keyword}: {e}")
            continue

    print(f"AliExpress API: {len(todos)} produtos encontrados")
    return todos


def buscar_ticket_baixo():
    """Busca dedicada para produtos até R$200 — ciclo das 19:00."""
    todos = []
    vistos = set()
    preco_teto = float(os.getenv("PRECO_TICKET_BAIXO", "200.0"))
    # Teto em USD usando cotacao configuravel (padrao 5.80)
    preco_teto_usd = str(int(preco_teto / TB_COTACAO_USD))

    for keyword in CATEGORIAS_TICKET_BAIXO:
        try:
            timestamp = str(int(time.time() * 1000))
            params = {
                "app_key":         ALIEXPRESS_APP_KEY,
                "timestamp":       timestamp,
                "sign_method":     "md5",
                "method":          "aliexpress.affiliate.product.query",
                "keywords":        keyword,
                "page_no":         str(random.randint(1, 3)),
                "page_size":       "8",
                "sort":            "LAST_VOLUME_DESC",
                "min_sale_price":  PRECO_MIN_USD,
                "max_sale_price":  preco_teto_usd,
                "target_currency": "BRL",
                "target_language": "PT",
                "tracking_id":     ALIEXPRESS_TRACKING,
                "ship_to_country": "BR",
                "fields":          "product_id,product_title,target_sale_price,target_original_price,target_sale_price_currency,discount,evaluate_rate,lastest_volume,product_main_image_url,promotion_link",
            }
            params["sign"] = gerar_assinatura(params, ALIEXPRESS_APP_SECRET)
            r = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15)
            if r.status_code != 200:
                continue
            data = r.json()
            resp = data.get("aliexpress_affiliate_product_query_response", {})
            result = resp.get("resp_result", {})
            if result.get("resp_code") != 200:
                continue
            items = result.get("result", {}).get("products", {}).get("product", [])
            for item in items:
                try:
                    preco = float(str(item.get("target_sale_price", "0")).replace(",", "."))
                    preco_orig = float(str(item.get("target_original_price", "0")).replace(",", "."))
                except:
                    continue
                if preco < TB_PRECO_MINIMO or preco > preco_teto:
                    continue
                desconto = int((1 - preco / preco_orig) * 100) if preco_orig > preco else 0
                if desconto < TB_DESCONTO_MINIMO:
                    continue
                nome = item.get("product_title", "")
                link_original = item.get("promotion_link", "")
                imagem = item.get("product_main_image_url", "")
                if not nome or not link_original:
                    continue
                if not produto_valido(nome):
                    continue
                chave = hashlib.md5(nome.encode()).hexdigest()
                if chave in vistos:
                    continue
                vistos.add(chave)
                link = encurtar_link(link_original)
                todos.append({
                    "nome": nome, "preco": round(preco, 2),
                    "preco_original": round(preco_orig, 2),
                    "desconto": desconto, "loja": "ALIEXPRESS",
                    "frete": "🚢 Frete grátis", "link_afiliado": link,
                    "imagem_url": imagem, "score": 1, "fontes": ["aliexpress"],
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"AliExpress ticket baixo erro ({keyword}): {e}")
            continue

    print(f"AliExpress ticket baixo: {len(todos)} produtos encontrados (≤R${preco_teto:.0f})")
    return todos
