"""
OlhaissoTech Bot v2.0
Fontes: Google Trends BR + Amazon Best Sellers + Reddit Gadgets + Shopee Afiliados
Lógica: produtos que aparecem em 2+ fontes têm prioridade máxima
"""

import os
import time
import json
import hashlib
import logging
import schedule
import requests
import textwrap
from io import BytesIO
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("OlhaissoTech")

# ============================================================
# CONFIGURAÇÕES
# ============================================================
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "8258862380:AAGCr--OpycbKXp6KeqJCU1_piyu4kRl4bk")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@olhaissotech")
AMAZON_TAG       = os.getenv("AMAZON_TAG", "olhaissotech-20")
SHOPEE_APP_ID    = os.getenv("SHOPEE_APP_ID", "")
SHOPEE_SECRET    = os.getenv("SHOPEE_SECRET", "")

PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "300"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))
HORARIOS        = ["08:00", "11:00", "14:00", "17:00", "20:00", "22:00"]

# Palavras-chave do nicho para filtrar tendências relevantes
KEYWORDS_NICHO = [
    "gadget", "fone", "carregador", "teclado", "mouse", "câmera",
    "smartwatch", "speaker", "bluetooth", "usb", "led", "robô",
    "aspirador", "fritadeira", "airfryer", "projetor", "drone",
    "cabo", "hub", "power bank", "earphone", "headset", "webcam",
    "luminária", "lâmpada", "tomada inteligente", "smart home",
    "impressora", "tablet", "celular", "notebook", "monitor",
    "suporte", "cooler", "rgb", "gamer", "pen drive", "ssd"
]

# ============================================================
# CORES E ESTILO
# ============================================================
COR_FUNDO        = (17, 17, 17)
COR_CARD         = (26, 26, 26)
COR_LARANJA      = (255, 107, 26)
COR_LARANJA_CLARO= (255, 154, 74)
COR_VERDE        = (0, 187, 68)
COR_BRANCO       = (255, 255, 255)
COR_CINZA        = (136, 136, 136)
COR_CINZA_ESCURO = (45, 45, 45)

# ============================================================
# FONTES DE TENDÊNCIA
# ============================================================

def buscar_trends_google():
    """
    Google Trends BR — palavras do nicho em alta agora.
    Retorna lista de termos em crescimento.
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="pt-BR", tz=-180, timeout=(10, 25))
        termos_em_alta = []

        for i in range(0, len(KEYWORDS_NICHO), 5):
            lote = KEYWORDS_NICHO[i:i+5]
            try:
                pt.build_payload(lote, geo="BR", timeframe="now 1-d")
                dados = pt.interest_over_time()
                if dados.empty:
                    continue
                media = dados[lote].mean()
                for termo in lote:
                    if media.get(termo, 0) > 40:
                        termos_em_alta.append(termo)
                time.sleep(1.5)
            except Exception:
                continue

        log.info(f"Google Trends: {len(termos_em_alta)} termos em alta no BR")
        return termos_em_alta

    except ImportError:
        log.warning("pytrends não instalado — pulando Google Trends")
        return []
    except Exception as e:
        log.warning(f"Google Trends erro: {e}")
        return []


def buscar_amazon_best_sellers():
    """
    Amazon BR Best Sellers — eletrônicos e informática.
    Faz scraping das páginas públicas de mais vendidos.
    """
    categorias = [
        ("Eletrônicos", "https://www.amazon.com.br/gp/bestsellers/electronics"),
        ("Informática", "https://www.amazon.com.br/gp/bestsellers/computers"),
        ("Utilidades Domésticas", "https://www.amazon.com.br/gp/bestsellers/kitchen"),
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    produtos = []

    for nome_cat, url in categorias:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue

            from html.parser import HTMLParser

            class AmazonParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.items = []
                    self._in_title = False
                    self._in_price = False
                    self._current = {}

                def handle_starttag(self, tag, attrs):
                    attrs = dict(attrs)
                    cls = attrs.get("class", "")
                    if "p13n-sc-truncate" in cls or "_p13n-zg-list-grid-desktop_style_p13n-zg-item" in cls:
                        self._in_title = True
                    if "p13n-sc-price" in cls:
                        self._in_price = True

                def handle_data(self, data):
                    data = data.strip()
                    if not data:
                        return
                    if self._in_title and len(data) > 8:
                        self._current["nome"] = data
                        self._in_title = False
                    if self._in_price and "R$" in data:
                        self._current["preco_txt"] = data
                        if "nome" in self._current:
                            self.items.append(dict(self._current))
                            self._current = {}
                        self._in_price = False

            parser = AmazonParser()
            parser.feed(r.text)

            for item in parser.items[:10]:
                nome = item.get("nome", "")
                preco_txt = item.get("preco_txt", "0")
                try:
                    preco = float(
                        preco_txt.replace("R$", "").replace(".", "").replace(",", ".").strip()
                    )
                except:
                    preco = 0

                if preco <= 0 or preco > PRECO_MAXIMO:
                    continue

                asin = hashlib.md5(nome.encode()).hexdigest()[:10]
                link = f"https://www.amazon.com.br/dp/{asin}?tag={AMAZON_TAG}"

                produtos.append({
                    "nome": nome,
                    "preco": preco,
                    "preco_original": round(preco * 1.3, 2),
                    "desconto": 23,
                    "loja": "AMAZON",
                    "frete": "✅ Frete grátis Prime",
                    "link_afiliado": link,
                    "imagem_url": "",
                    "categoria": nome_cat,
                    "score": 1,
                    "fontes": ["amazon"],
                })

            log.info(f"Amazon {nome_cat}: {len(parser.items[:10])} produtos")
            time.sleep(2)

        except Exception as e:
            log.warning(f"Amazon erro ({nome_cat}): {e}")

    return produtos


def buscar_reddit_gadgets():
    """
    Reddit r/gadgets e r/BuyItForLife — novidades tech.
    API pública do Reddit, sem autenticação.
    """
    subreddits = ["gadgets", "BuyItForLife", "malelifestyle"]
    headers = {"User-Agent": "OlhaissoTechBot/2.0"}
    termos = []

    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                continue

            posts = r.json().get("data", {}).get("children", [])
            for post in posts:
                titulo = post["data"].get("title", "").lower()
                score = post["data"].get("score", 0)
                if score < 500:
                    continue
                for kw in KEYWORDS_NICHO:
                    if kw in titulo:
                        termos.append(kw)

            log.info(f"Reddit r/{sub}: {len(posts)} posts analisados")
            time.sleep(1)

        except Exception as e:
            log.warning(f"Reddit erro ({sub}): {e}")

    return list(set(termos))


def buscar_tiktok_trending():
    """
    TikTok Creative Center Top Products — produtos viralizando.
    Usa endpoint público sem autenticação.
    """
    try:
        url = "https://ads.tiktok.com/creative_radar_api/v1/top_product/list"
        params = {
            "period": 7,
            "page": 1,
            "limit": 20,
            "region": "BR",
            "category_id": 0,
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://ads.tiktok.com/business/creativecenter/",
        }
        r = requests.get(url, params=params, headers=headers, timeout=10)

        if r.status_code == 200:
            dados = r.json().get("data", {}).get("list", [])
            termos = []
            for item in dados:
                nome = item.get("product_name", "").lower()
                for kw in KEYWORDS_NICHO:
                    if kw in nome:
                        termos.append(kw)
            log.info(f"TikTok Creative Center: {len(termos)} termos detectados")
            return list(set(termos))

    except Exception as e:
        log.warning(f"TikTok Creative Center erro: {e}")

    return []


def buscar_shopee_afiliados():
    """
    Shopee Afiliados API — produtos em destaque.
    Ativo após aprovação com credenciais.
    """
    if not SHOPEE_APP_ID or not SHOPEE_SECRET:
        log.info("Shopee: aguardando credenciais de afiliado")
        return []

    try:
        import hmac
        import hashlib as hl

        timestamp = int(time.time())
        base_string = f"{SHOPEE_APP_ID}{timestamp}"
        signature = hmac.new(
            SHOPEE_SECRET.encode(),
            base_string.encode(),
            hl.sha256
        ).hexdigest()

        headers = {
            "Authorization": f"SHA256 {SHOPEE_APP_ID}:{timestamp}:{signature}",
            "Content-Type": "application/json",
        }

        payload = {
            "keyword": "gadget",
            "sortType": 2,
            "limit": 20,
            "page": 1,
        }

        r = requests.post(
            "https://open-api.affiliate.shopee.com.br/graphql",
            headers=headers,
            json=payload,
            timeout=15
        )

        if r.status_code == 200:
            items = r.json().get("data", {}).get("productOfferV2", {}).get("nodes", [])
            produtos = []
            for item in items:
                preco = item.get("priceMin", 0) / 100000
                if preco > PRECO_MAXIMO:
                    continue
                produtos.append({
                    "nome": item.get("productName", ""),
                    "preco": preco,
                    "preco_original": preco * 1.4,
                    "desconto": item.get("discountRate", 0),
                    "loja": "SHOPEE",
                    "frete": "✅ Frete grátis",
                    "link_afiliado": item.get("offerLink", ""),
                    "imagem_url": item.get("imageUrl", ""),
                    "score": 1,
                    "fontes": ["shopee"],
                })
            log.info(f"Shopee: {len(produtos)} produtos")
            return produtos

    except Exception as e:
        log.warning(f"Shopee erro: {e}")

    return []


# ============================================================
# MOTOR DE SCORE — cruza fontes e prioriza
# ============================================================

def calcular_score(produto, trends_google, trends_tiktok, trends_reddit):
    """
    Calcula score de prioridade do produto.
    Cada fonte confirma +1 ponto. Máximo = 4.
    """
    score = produto.get("score", 0)
    nome = produto.get("nome", "").lower()
    fontes = produto.get("fontes", [])

    for kw in KEYWORDS_NICHO:
        if kw not in nome:
            continue
        if kw in trends_google and "google" not in fontes:
            score += 1
            fontes.append("google")
        if kw in trends_tiktok and "tiktok" not in fontes:
            score += 1
            fontes.append("tiktok")
        if kw in trends_reddit and "reddit" not in fontes:
            score += 1
            fontes.append("reddit")

    produto["score"] = score
    produto["fontes"] = fontes
    return produto


def montar_pipeline():
    """
    Coleta todas as fontes, cruza dados e retorna
    produtos ordenados por score (maior primeiro).
    """
    log.info("=== Iniciando pipeline de busca ===")

    # 1. Tendências
    log.info("Buscando Google Trends BR...")
    trends_google = buscar_trends_google()

    log.info("Buscando TikTok Creative Center...")
    trends_tiktok = buscar_tiktok_trending()

    log.info("Buscando Reddit gadgets...")
    trends_reddit = buscar_reddit_gadgets()

    log.info(f"Tendências detectadas — Google: {len(trends_google)} | TikTok: {len(trends_tiktok)} | Reddit: {len(trends_reddit)}")

    # 2. Produtos com link de afiliado
    log.info("Buscando Amazon Best Sellers...")
    produtos = buscar_amazon_best_sellers()

    log.info("Buscando Shopee Afiliados...")
    produtos += buscar_shopee_afiliados()

    if not produtos:
        log.warning("Nenhum produto encontrado nas fontes — usando mock")
        produtos = produtos_mock()

    # 3. Filtrar por preço e desconto
    produtos = [
        p for p in produtos
        if p.get("preco", 999) <= PRECO_MAXIMO
        and p.get("desconto", 0) >= DESCONTO_MINIMO
    ]

    # 4. Calcular score cruzando fontes
    for p in produtos:
        calcular_score(p, trends_google, trends_tiktok, trends_reddit)

    # 5. Ordenar por score (prioridade máxima = mais fontes confirmando)
    produtos.sort(key=lambda x: x.get("score", 0), reverse=True)

    log.info(f"Pipeline concluído: {len(produtos)} produtos prontos")
    for p in produtos[:5]:
        log.info(f"  [{p['score']}pts] {p['nome'][:50]} — Fontes: {p['fontes']}")

    return produtos


def produtos_mock():
    """Produtos de teste enquanto APIs não estão configuradas."""
    return [
        {
            "nome": "Fone Bluetooth TWS 5.3 com cancelamento de ruído",
            "preco": 72.90, "preco_original": 189.90, "desconto": 62,
            "loja": "SHOPEE", "frete": "✅ Frete grátis",
            "link_afiliado": "https://s.shopee.com.br/exemplo",
            "imagem_url": "", "score": 3, "fontes": ["shopee", "google", "tiktok"],
        },
        {
            "nome": "Carregador GaN 65W turbo 3 portas USB-C",
            "preco": 49.90, "preco_original": 129.00, "desconto": 61,
            "loja": "SHOPEE", "frete": "✅ Frete grátis",
            "link_afiliado": "https://s.shopee.com.br/exemplo2",
            "imagem_url": "", "score": 2, "fontes": ["shopee", "tiktok"],
        },
        {
            "nome": "Aspirador robô Wi-Fi com mapeamento automático",
            "preco": 249.90, "preco_original": 499.90, "desconto": 50,
            "loja": "AMAZON", "frete": "✅ Frete grátis Prime",
            "link_afiliado": f"https://amzn.to/exemplo?tag={AMAZON_TAG}",
            "imagem_url": "", "score": 3, "fontes": ["amazon", "google", "reddit"],
        },
    ]


# ============================================================
# GERADOR DE IMAGEM
# ============================================================

def carregar_fonte(tamanho, negrito=False):
    nomes = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if negrito else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if negrito else '-Regular'}.ttf",
    ]
    for nome in nomes:
        try:
            return ImageFont.truetype(nome, tamanho)
        except:
            continue
    return ImageFont.load_default()


def badge_score(score):
    """Converte score em label de tendência."""
    if score >= 3:
        return ("🔥 VIRAL AGORA", COR_LARANJA)
    elif score == 2:
        return ("📈 TENDÊNCIA", (0, 150, 200))
    else:
        return ("💰 OFERTA", COR_VERDE)


def gerar_imagem(produto):
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), COR_FUNDO)
    draw = ImageDraw.Draw(img)

    # Card
    draw.rounded_rectangle([32, 32, W-32, H-32], radius=36, fill=COR_CARD)

    # Topo — badge score (esquerda)
    label_score, cor_score = badge_score(produto.get("score", 0))
    draw.rounded_rectangle([60, 60, 60+220, 60+44], radius=22, fill=cor_score)
    f_badge = carregar_fonte(19, negrito=True)
    bb = draw.textbbox((0,0), label_score, font=f_badge)
    draw.text((60+(220-(bb[2]-bb[0]))//2, 60+12), label_score, font=f_badge, fill=COR_BRANCO)

    # Topo — badge loja (centro)
    loja = produto.get("loja", "SHOPEE")
    draw.rounded_rectangle([W//2-70, 60, W//2+70, 60+44], radius=22, fill=(40,40,40))
    bb2 = draw.textbbox((0,0), loja, font=f_badge)
    draw.text((W//2-(bb2[2]-bb2[0])//2, 60+12), loja, font=f_badge, fill=COR_LARANJA)

    # Topo — badge desconto (direita)
    desc = produto.get("desconto", 0)
    if desc > 0:
        desc_txt = f"-{desc}%"
        draw.rounded_rectangle([W-60-130, 60, W-60, 60+44], radius=22, fill=COR_VERDE)
        bb3 = draw.textbbox((0,0), desc_txt, font=f_badge)
        draw.text((W-60-130+(130-(bb3[2]-bb3[0]))//2, 60+12), desc_txt, font=f_badge, fill=COR_BRANCO)

    # Imagem do produto
    img_url = produto.get("imagem_url", "")
    prod_img = None
    if img_url:
        try:
            r = requests.get(img_url, timeout=8)
            prod_img = Image.open(BytesIO(r.content)).convert("RGBA")
            prod_img = prod_img.resize((500, 420), Image.LANCZOS)
        except:
            prod_img = None

    if prod_img:
        img.paste(prod_img, ((W-500)//2, 130), prod_img)
    else:
        draw.rounded_rectangle([240, 130, 840, 570], radius=20, fill=COR_CINZA_ESCURO)
        f_ico = carregar_fonte(90)
        draw.text((540, 350), "📦", font=f_ico, fill=(70,70,70), anchor="mm")

    # Linha separadora
    draw.rectangle([60, 590, W-60, 592], fill=COR_CINZA_ESCURO)

    # Fontes de tendência detectadas
    fontes = produto.get("fontes", [])
    labels_fontes = {
        "google": "Google Trends", "tiktok": "TikTok Viral",
        "reddit": "Reddit", "amazon": "Amazon BR", "shopee": "Shopee BR"
    }
    txt_fontes = " · ".join([labels_fontes.get(f, f) for f in fontes])
    if txt_fontes:
        f_sub = carregar_fonte(20)
        bb = draw.textbbox((0,0), txt_fontes, font=f_sub)
        draw.text(((W-(bb[2]-bb[0]))//2, 604), txt_fontes, font=f_sub, fill=COR_CINZA)

    # Nome do produto
    f_nome = carregar_fonte(38, negrito=True)
    nome = produto.get("nome", "")
    linhas = textwrap.wrap(nome, width=32)[:2]
    y = 638
    for linha in linhas:
        bb = draw.textbbox((0,0), linha, font=f_nome)
        draw.text(((W-(bb[2]-bb[0]))//2, y), linha, font=f_nome, fill=COR_BRANCO)
        y += 50

    # Preço original riscado
    preco_orig = produto.get("preco_original", 0)
    if preco_orig > 0:
        f_old = carregar_fonte(28)
        txt_old = f"De R$ {preco_orig:.2f}".replace(".", ",")
        bb = draw.textbbox((0,0), txt_old, font=f_old)
        x_old = (W-(bb[2]-bb[0]))//2
        draw.text((x_old, y+10), txt_old, font=f_old, fill=COR_CINZA)
        draw.line([(x_old, y+26), (x_old+(bb[2]-bb[0]), y+26)], fill=COR_CINZA, width=2)
        y += 52

    # Preço atual
    f_preco = carregar_fonte(82, negrito=True)
    preco = produto.get("preco", 0)
    txt_preco = f"R$ {preco:.2f}".replace(".", ",")
    bb = draw.textbbox((0,0), txt_preco, font=f_preco)
    draw.text(((W-(bb[2]-bb[0]))//2, y+8), txt_preco, font=f_preco, fill=COR_LARANJA)

    # Frete
    frete = produto.get("frete", "")
    if frete:
        f_frete = carregar_fonte(24)
        bb = draw.textbbox((0,0), frete, font=f_frete)
        draw.text(((W-(bb[2]-bb[0]))//2, y+102), frete, font=f_frete, fill=COR_VERDE)

    # Rodapé laranja
    draw.rounded_rectangle([32, H-110, W-32, H-32], radius=28, fill=COR_LARANJA)
    f_cta = carregar_fonte(30, negrito=True)
    cta = "👀  Link na bio e no canal do Telegram!"
    bb = draw.textbbox((0,0), cta, font=f_cta)
    draw.text(((W-(bb[2]-bb[0]))//2, H-88), cta, font=f_cta, fill=COR_BRANCO)

    # Salvar
    path = f"/tmp/oferta_{hashlib.md5(nome.encode()).hexdigest()[:8]}.jpg"
    img.save(path, "JPEG", quality=93)
    return path


# ============================================================
# TELEGRAM
# ============================================================

def montar_caption(produto):
    nome   = produto.get("nome", "")
    preco  = produto.get("preco", 0)
    orig   = produto.get("preco_original", 0)
    desc   = produto.get("desconto", 0)
    link   = produto.get("link_afiliado", "")
    loja   = produto.get("loja", "")
    frete  = produto.get("frete", "")
    score  = produto.get("score", 0)
    fontes = produto.get("fontes", [])

    # Emoji de urgência baseado no score
    urgencia = "🔥🔥🔥" if score >= 3 else "🔥🔥" if score == 2 else "🔥"

    economia = round(orig - preco, 2) if orig > preco else 0

    txt = f"{urgencia} *{nome}*\n\n"

    if desc > 0:
        txt += f"📉 *{desc}% de desconto!*\n"
    if economia > 0:
        txt += f"💸 Economia de R$ {str(economia).replace('.', ',')}\n"

    txt += f"\n💰 *R$ {str(preco).replace('.', ',')}*"
    if orig > 0:
        txt += f" ~~R$ {str(orig).replace('.', ',')}~~"

    txt += f"\n\n🏪 {loja}"
    if frete:
        txt += f"\n{frete}"

    if fontes:
        labels = {"google": "Google Trends", "tiktok": "TikTok", "reddit": "Reddit", "amazon": "Amazon", "shopee": "Shopee"}
        txt += f"\n📊 Em alta: {' · '.join([labels.get(f,f) for f in fontes])}"

    txt += f"\n\n🛒 [Comprar agora — clique aqui]({link})"
    txt += f"\n\n_👀 OlhaissoTech — Gadgets e utilidades com o melhor preço_"

    return txt


def postar_telegram(produto, imagem_path):
    caption = montar_caption(produto)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(imagem_path, "rb") as f:
            r = requests.post(url, data={
                "chat_id": TELEGRAM_CHANNEL,
                "caption": caption,
                "parse_mode": "Markdown",
            }, files={"photo": f}, timeout=30)
        ok = r.status_code == 200
        if not ok:
            log.error(f"Telegram erro: {r.text[:200]}")
        return ok
    except Exception as e:
        log.error(f"Telegram exceção: {e}")
        return False


# ============================================================
# CICLO PRINCIPAL
# ============================================================
postados = set()

def ciclo():
    log.info(f"\n{'='*50}")
    log.info(f"Ciclo iniciado — {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    produtos = montar_pipeline()

    postou = 0
    for produto in produtos:
        chave = hashlib.md5(produto["nome"].encode()).hexdigest()
        if chave in postados:
            continue

        log.info(f"Postando [{produto['score']}pts]: {produto['nome'][:50]}")
        imagem = gerar_imagem(produto)
        ok = postar_telegram(produto, imagem)

        if ok:
            postados.add(chave)
            postou += 1
            log.info("✅ Postado com sucesso!")
        else:
            log.error("❌ Falha ao postar")

        if postou >= 2:
            break
        time.sleep(8)

    log.info(f"Ciclo concluído — {postou} post(s) enviado(s)\n")


def main():
    log.info("🤖 OlhaissoTech Bot v2.0 iniciado!")
    log.info(f"📢 Canal: {TELEGRAM_CHANNEL}")
    log.info(f"⏰ Horários: {', '.join(HORARIOS)}")
    log.info(f"🎯 Filtros: preço até R${PRECO_MAXIMO} | desconto mín. {DESCONTO_MINIMO}%\n")

    for h in HORARIOS:
        schedule.every().day.at(h).do(ciclo)

    ciclo()  # Roda imediatamente ao iniciar

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
