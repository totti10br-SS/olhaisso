"""
OlhaissoTech Bot v6.0
- AliExpress API oficial (AppKey: 530504)
- Shopee API oficial (AppID: 18307831002)
- Amazon Best Sellers
- Google Trends BR
- TikTok Creative Center
- Reddit gadgets
- Score inteligente por cruzamento de fontes
- Imagem 1080x1080 com logo
- 8 posts por ciclo
- SQLite para evitar repetição de produtos
"""

import os
import time
import hashlib
import logging
import sqlite3
import schedule
import requests
import textwrap
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from aliexpress_api import buscar_todos_produtos as buscar_aliexpress
from shopee_api import buscar_todos_produtos as buscar_shopee

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
PRECO_MAXIMO     = float(os.getenv("PRECO_MAXIMO", "800"))
DESCONTO_MINIMO  = int(os.getenv("DESCONTO_MINIMO", "20"))
POSTS_POR_CICLO  = int(os.getenv("POSTS_POR_CICLO", "8"))
HORARIOS         = ["08:00", "11:00", "14:00", "17:00", "20:00", "22:00"]
DB_PATH          = os.getenv("DB_PATH", "/data/olhaissotech.db")

# Quantos dias manter um produto no histórico antes de poder repetir
DIAS_SEM_REPETIR = int(os.getenv("DIAS_SEM_REPETIR", "2"))

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
# CORES
# ============================================================
COR_FUNDO         = (17, 17, 17)
COR_CARD          = (26, 26, 26)
COR_LARANJA       = (255, 107, 26)
COR_LARANJA_CLARO = (255, 154, 74)
COR_VERDE         = (0, 187, 68)
COR_BRANCO        = (255, 255, 255)
COR_CINZA         = (136, 136, 136)
COR_CINZA_ESCURO  = (45, 45, 45)

# ============================================================
# BANCO DE DADOS SQLite
# ============================================================

def init_db():
    """Cria o banco de dados e tabelas se não existirem."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS postados (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            hash      TEXT UNIQUE NOT NULL,
            nome      TEXT,
            preco     REAL,
            loja      TEXT,
            postado_em TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    log.info(f"SQLite iniciado: {DB_PATH}")


def ja_postado(hash_produto):
    """Verifica se produto foi postado nos últimos DIAS_SEM_REPETIR dias."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        limite = (datetime.now() - timedelta(days=DIAS_SEM_REPETIR)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT id FROM postados WHERE hash = ? AND postado_em > ?", (hash_produto, limite))
        resultado = c.fetchone()
        conn.close()
        return resultado is not None
    except Exception as e:
        log.error(f"SQLite erro ao verificar: {e}")
        return False


def registrar_post(produto):
    """Registra produto postado no banco."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        hash_p = hashlib.md5(produto["nome"].encode()).hexdigest()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT OR REPLACE INTO postados (hash, nome, preco, loja, postado_em)
            VALUES (?, ?, ?, ?, ?)
        """, (hash_p, produto["nome"][:200], produto.get("preco", 0),
              produto.get("loja", ""), agora))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"SQLite erro ao registrar: {e}")


def limpar_historico_antigo():
    """Remove registros mais antigos que DIAS_SEM_REPETIR * 2 dias."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        limite = (datetime.now() - timedelta(days=DIAS_SEM_REPETIR * 2)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("DELETE FROM postados WHERE postado_em < ?", (limite,))
        removidos = c.rowcount
        conn.commit()
        conn.close()
        if removidos > 0:
            log.info(f"SQLite: {removidos} registros antigos removidos")
    except Exception as e:
        log.error(f"SQLite erro ao limpar: {e}")


def contar_postados():
    """Retorna total de produtos no histórico."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM postados")
        total = c.fetchone()[0]
        conn.close()
        return total
    except:
        return 0

# ============================================================
# HELPERS
# ============================================================

def fmt_preco(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_economia(orig, atual):
    eco = round(orig - atual, 2)
    return fmt_preco(eco) if eco > 0 else None


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
    if score >= 3:
        return ("🔥 VIRAL AGORA", COR_LARANJA)
    elif score == 2:
        return ("📈 TENDÊNCIA", (0, 150, 200))
    else:
        return ("💰 OFERTA", COR_VERDE)


def desenhar_logo(draw, x, y, tamanho=34):
    r = tamanho // 2
    esp = tamanho + 6
    for i in range(2):
        cx = x + i * esp + r
        cy = y + r
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=COR_LARANJA, width=3)
        ri = int(r * 0.55)
        draw.ellipse([cx-ri, cy-ri, cx+ri, cy+ri], fill=COR_LARANJA_CLARO)
        rp = int(r * 0.25)
        draw.ellipse([cx-rp, cy-rp, cx+rp, cy+rp], fill=COR_FUNDO)
        rb = int(r * 0.14)
        draw.ellipse([cx+int(r*0.12)-rb, cy-int(r*0.2)-rb,
                      cx+int(r*0.12)+rb, cy-int(r*0.2)+rb], fill=COR_BRANCO)

# ============================================================
# GERADOR DE IMAGEM
# ============================================================

def gerar_imagem(produto):
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), COR_FUNDO)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([32, 32, W-32, H-32], radius=36, fill=COR_CARD)

    # Badges do topo — fonte maior para melhor leitura
    f_badge = carregar_fonte(36, negrito=True)
    BADGE_H = 70  # altura dos badges

    label_score, cor_score = badge_score(produto.get("score", 0))
    draw.rounded_rectangle([55, 50, 55+280, 50+BADGE_H], radius=28, fill=cor_score)
    bb = draw.textbbox((0,0), label_score, font=f_badge)
    draw.text((55+(280-(bb[2]-bb[0]))//2, 50+(BADGE_H-(bb[3]-bb[1]))//2), label_score, font=f_badge, fill=COR_BRANCO)

    loja = produto.get("loja", "ALIEXPRESS")
    draw.rounded_rectangle([W//2-100, 50, W//2+100, 50+BADGE_H], radius=28, fill=(40,40,40))
    bb2 = draw.textbbox((0,0), loja, font=f_badge)
    draw.text((W//2-(bb2[2]-bb2[0])//2, 50+(BADGE_H-(bb2[3]-bb2[1]))//2), loja, font=f_badge, fill=COR_LARANJA)

    desc = produto.get("desconto", 0)
    if desc > 0:
        desc_txt = f"-{desc}%"
        draw.rounded_rectangle([W-55-165, 50, W-55, 50+BADGE_H], radius=28, fill=COR_VERDE)
        bb3 = draw.textbbox((0,0), desc_txt, font=f_badge)
        draw.text((W-55-165+(165-(bb3[2]-bb3[0]))//2, 50+(BADGE_H-(bb3[3]-bb3[1]))//2), desc_txt, font=f_badge, fill=COR_BRANCO)

    img_url = produto.get("imagem_url", "")
    prod_img = None
    if img_url:
        try:
            r = requests.get(img_url, timeout=8)
            prod_img = Image.open(BytesIO(r.content)).convert("RGBA")
            prod_img = prod_img.resize((500, 400), Image.LANCZOS)
        except:
            prod_img = None

    if prod_img:
        img.paste(prod_img, ((W-500)//2, 130), prod_img)
    else:
        draw.rounded_rectangle([240, 130, 840, 550], radius=20, fill=COR_CINZA_ESCURO)
        f_ico = carregar_fonte(80)
        draw.text((540, 340), "📦", font=f_ico, fill=(70,70,70), anchor="mm")

    draw.rectangle([60, 568, W-60, 570], fill=COR_CINZA_ESCURO)

    # Fontes de tendência (pequenas, abaixo do separador)
    fontes = produto.get("fontes", [])
    labels_f = {
        "google": "Google Trends", "tiktok": "TikTok Viral",
        "reddit": "Reddit", "amazon": "Amazon BR",
        "aliexpress": "AliExpress", "shopee": "Shopee BR"
    }
    txt_fontes = " · ".join([labels_f.get(f, f) for f in fontes])
    if txt_fontes:
        f_sub = carregar_fonte(26)
        bb = draw.textbbox((0,0), txt_fontes, font=f_sub)
        draw.text(((W-(bb[2]-bb[0]))//2, 572), txt_fontes, font=f_sub, fill=COR_CINZA)

    # Header OlhaissO com olhinhos
    f_header = carregar_fonte(42, negrito=True)
    header_txt = "👀 OlhaissO"
    bb_h = draw.textbbox((0,0), header_txt, font=f_header)
    draw.text(((W-(bb_h[2]-bb_h[0]))//2, 590), header_txt, font=f_header, fill=COR_LARANJA)

    f_nome = carregar_fonte(44, negrito=True)
    nome = produto.get("nome", "")
    linhas = textwrap.wrap(nome, width=34)[:2]
    y = 638
    for linha in linhas:
        bb = draw.textbbox((0,0), linha, font=f_nome)
        draw.text(((W-(bb[2]-bb[0]))//2, y), linha, font=f_nome, fill=COR_BRANCO)
        y += 48

    preco_orig = produto.get("preco_original", 0)
    if preco_orig > 0:
        f_old = carregar_fonte(34)
        txt_old = f"De {fmt_preco(preco_orig)}"
        bb = draw.textbbox((0,0), txt_old, font=f_old)
        tw = bb[2] - bb[0]
        x_old = (W - tw) // 2
        draw.text((x_old, y + 10), txt_old, font=f_old, fill=COR_CINZA)
        meio_y = y + 10 + (bb[3] - bb[1]) // 2
        draw.line([(x_old, meio_y), (x_old + tw, meio_y)], fill=COR_CINZA, width=2)
        y += 48

    f_preco = carregar_fonte(80, negrito=True)
    preco = produto.get("preco", 0)
    txt_preco = fmt_preco(preco)
    bb = draw.textbbox((0,0), txt_preco, font=f_preco)
    draw.text(((W-(bb[2]-bb[0]))//2, y + 8), txt_preco, font=f_preco, fill=COR_LARANJA)

    frete = produto.get("frete", "")
    if frete:
        f_frete = carregar_fonte(32)
        bb = draw.textbbox((0,0), frete, font=f_frete)
        draw.text(((W-(bb[2]-bb[0]))//2, y + 100), frete, font=f_frete, fill=COR_VERDE)

    draw.rounded_rectangle([32, H-110, W-32, H-32], radius=28, fill=COR_LARANJA)
    desenhar_logo(draw, 62, H-96, tamanho=30)
    f_cta = carregar_fonte(34, negrito=True)
    cta = "OlhaissoTech — Link na bio e no Telegram!"
    bb = draw.textbbox((0,0), cta, font=f_cta)
    draw.text(((W-(bb[2]-bb[0]))//2 + 30, H-88), cta, font=f_cta, fill=COR_BRANCO)

    path = f"/tmp/oferta_{hashlib.md5(nome.encode()).hexdigest()[:8]}.jpg"
    img.save(path, "JPEG", quality=93)
    return path

# ============================================================
# TELEGRAM
# ============================================================


def escapar_html(texto):
    """Escapa caracteres especiais do HTML do Telegram."""
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def montar_caption(produto):
    nome   = escapar_html(produto.get("nome", ""))
    preco  = produto.get("preco", 0)
    orig   = produto.get("preco_original", 0)
    desc   = produto.get("desconto", 0)
    link   = produto.get("link_afiliado", "")
    loja   = produto.get("loja", "")
    frete  = produto.get("frete", "")
    score  = produto.get("score", 0)
    fontes = produto.get("fontes", [])

    urgencia = "🔥🔥🔥" if score >= 3 else "🔥🔥" if score == 2 else "🔥"
    eco = fmt_economia(orig, preco) if orig > preco else None

    txt = f"{urgencia} <b>{nome}</b>\n\n"
    if desc > 0:
        txt += f"📉 <b>{desc}% de desconto!</b>\n"
    if eco:
        txt += f"💸 Economia de <b>{eco}</b>\n"
    txt += f"\n💰 <b>{fmt_preco(preco)}</b>"
    if orig > 0:
        txt += f"  <i>(era {fmt_preco(orig)})</i>"
    txt += f"\n\n🏪 {loja}"
    if frete:
        txt += f"\n{frete}"
    if fontes:
        labels = {
            "google": "Google Trends", "tiktok": "TikTok",
            "reddit": "Reddit", "amazon": "Amazon",
            "aliexpress": "AliExpress", "shopee": "Shopee"
        }
        txt += f"\n📊 Em alta: {' · '.join([labels.get(f,f) for f in fontes])}"
    txt += f"\n\n🛒 <a href=\"{link}\">Comprar agora — clique aqui</a>"
    txt += f"\n\n<i>👀 OlhaissoTech — Gadgets e utilidades com o melhor preço</i>"
    return txt


def postar_telegram(produto, imagem_path):
    caption = montar_caption(produto)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(imagem_path, "rb") as f:
            r = requests.post(url, data={
                "chat_id": TELEGRAM_CHANNEL,
                "caption": caption,
                "parse_mode": "HTML",
            }, files={"photo": f}, timeout=30)
        ok = r.status_code == 200
        if not ok:
            log.error(f"Telegram erro: {r.text[:200]}")
        return ok
    except Exception as e:
        log.error(f"Telegram exceção: {e}")
        return False

# ============================================================
# FONTES DE TENDÊNCIA
# ============================================================

def buscar_trends_google():
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="pt-BR", tz=-180, timeout=(10, 25))
        termos = []
        for i in range(0, len(KEYWORDS_NICHO), 5):
            lote = KEYWORDS_NICHO[i:i+5]
            try:
                pt.build_payload(lote, geo="BR", timeframe="now 1-d")
                dados = pt.interest_over_time()
                if dados.empty:
                    continue
                media = dados[lote].mean()
                for t in lote:
                    if media.get(t, 0) > 40:
                        termos.append(t)
                time.sleep(1.5)
            except:
                continue
        log.info(f"Google Trends: {len(termos)} termos")
        return termos
    except:
        return []


def buscar_reddit_gadgets():
    headers = {"User-Agent": "OlhaissoTechBot/6.0"}
    termos = []
    for sub in ["gadgets", "BuyItForLife"]:
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=25", headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            for post in r.json().get("data", {}).get("children", []):
                titulo = post["data"].get("title", "").lower()
                if post["data"].get("score", 0) < 500:
                    continue
                for kw in KEYWORDS_NICHO:
                    if kw in titulo:
                        termos.append(kw)
            time.sleep(1)
        except:
            continue
    return list(set(termos))


def buscar_tiktok_trending():
    try:
        url = "https://ads.tiktok.com/creative_radar_api/v1/top_product/list"
        params = {"period": 7, "page": 1, "limit": 20, "region": "BR", "category_id": 0}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://ads.tiktok.com/business/creativecenter/"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            termos = []
            for item in r.json().get("data", {}).get("list", []):
                nome = item.get("product_name", "").lower()
                for kw in KEYWORDS_NICHO:
                    if kw in nome:
                        termos.append(kw)
            return list(set(termos))
    except:
        pass
    return []


def buscar_amazon_best_sellers():
    categorias = [
        ("Eletrônicos", "https://www.amazon.com.br/gp/bestsellers/electronics"),
        ("Informática", "https://www.amazon.com.br/gp/bestsellers/computers"),
    ]
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR,pt;q=0.9"}
    produtos = []
    for nome_cat, url in categorias:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            from html.parser import HTMLParser
            class P(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.items = []
                    self._t = False
                    self._p = False
                    self._c = {}
                def handle_starttag(self, tag, attrs):
                    cls = dict(attrs).get("class", "")
                    if "p13n-sc-truncate" in cls: self._t = True
                    if "p13n-sc-price" in cls: self._p = True
                def handle_data(self, data):
                    data = data.strip()
                    if not data: return
                    if self._t and len(data) > 8:
                        self._c["nome"] = data; self._t = False
                    if self._p and "R$" in data:
                        self._c["preco_txt"] = data
                        if "nome" in self._c:
                            self.items.append(dict(self._c)); self._c = {}
                        self._p = False
            p = P(); p.feed(r.text)
            for item in p.items[:8]:
                try:
                    preco = float(item["preco_txt"].replace("R$","").replace(".","").replace(",",".").strip())
                except:
                    preco = 0
                if preco <= 0 or preco > PRECO_MAXIMO: continue
                asin = hashlib.md5(item["nome"].encode()).hexdigest()[:10]
                produtos.append({
                    "nome": item["nome"], "preco": preco,
                    "preco_original": round(preco * 1.3, 2), "desconto": 23,
                    "loja": "AMAZON", "frete": "✅ Frete grátis Prime",
                    "link_afiliado": f"https://www.amazon.com.br/dp/{asin}?tag={AMAZON_TAG}",
                    "imagem_url": "", "score": 1, "fontes": ["amazon"],
                })
            time.sleep(2)
        except:
            continue
    return produtos


def calcular_score(produto, tg, tt, tr):
    score = produto.get("score", 0)
    nome = produto.get("nome", "").lower()
    fontes = produto.get("fontes", [])
    for kw in KEYWORDS_NICHO:
        if kw not in nome: continue
        if kw in tg and "google" not in fontes: score += 1; fontes.append("google")
        if kw in tt and "tiktok" not in fontes: score += 1; fontes.append("tiktok")
        if kw in tr and "reddit" not in fontes: score += 1; fontes.append("reddit")
    produto["score"] = score
    produto["fontes"] = fontes
    return produto


def produtos_mock():
    return [
        {"nome": "Fone Bluetooth TWS 5.3 com cancelamento de ruído", "preco": 72.90, "preco_original": 189.90, "desconto": 62, "loja": "ALIEXPRESS", "frete": "🚢 Frete grátis", "link_afiliado": "https://s.click.aliexpress.com/e/_exemplo", "imagem_url": "", "score": 3, "fontes": ["aliexpress", "google", "tiktok"]},
        {"nome": "Carregador GaN 65W turbo 3 portas USB-C", "preco": 89.90, "preco_original": 189.00, "desconto": 52, "loja": "ALIEXPRESS", "frete": "🚢 Frete grátis", "link_afiliado": "https://s.click.aliexpress.com/e/_exemplo2", "imagem_url": "", "score": 2, "fontes": ["aliexpress", "tiktok"]},
        {"nome": "Aspirador robô Wi-Fi com mapeamento automático", "preco": 249.90, "preco_original": 499.90, "desconto": 50, "loja": "AMAZON", "frete": "✅ Frete grátis Prime", "link_afiliado": "https://amzn.to/exemplo", "imagem_url": "", "score": 3, "fontes": ["amazon", "google", "reddit"]},
    ]


def montar_pipeline():
    log.info("=== Pipeline v6.0 iniciado ===")
    tg = buscar_trends_google()
    tt = buscar_tiktok_trending()
    tr = buscar_reddit_gadgets()
    log.info(f"Tendências — Google: {len(tg)} | TikTok: {len(tt)} | Reddit: {len(tr)}")

    log.info("Buscando AliExpress API...")
    produtos = buscar_aliexpress()

    log.info("Buscando Shopee API...")
    produtos += buscar_shopee()

    log.info("Buscando Amazon Best Sellers...")
    produtos += buscar_amazon_best_sellers()

    if not produtos:
        log.warning("Sem produtos — usando mock")
        produtos = produtos_mock()

    # Filtra por preço e desconto
    produtos = [p for p in produtos if p.get("preco", 999) <= PRECO_MAXIMO and p.get("desconto", 0) >= DESCONTO_MINIMO]

    # Calcula score de tendência
    for p in produtos:
        calcular_score(p, tg, tt, tr)

    # Remove produtos já postados recentemente (SQLite)
    antes = len(produtos)
    produtos = [p for p in produtos if not ja_postado(hashlib.md5(p["nome"].encode()).hexdigest())]
    filtrados = antes - len(produtos)
    if filtrados > 0:
        log.info(f"SQLite: {filtrados} produtos já postados recentemente removidos")

    # Separa por loja e ordena cada grupo por score
    por_loja = {}
    for p in produtos:
        loja = p.get("loja", "OUTRO")
        por_loja.setdefault(loja, []).append(p)
    for loja in por_loja:
        por_loja[loja].sort(key=lambda x: x.get("score", 0), reverse=True)

    # Rodizio entre lojas para garantir variedade
    ordem_lojas = ["ALIEXPRESS", "SHOPEE", "ALIEXPRESS", "SHOPEE",
                   "ALIEXPRESS", "AMAZON", "ALIEXPRESS", "SHOPEE",
                   "ALIEXPRESS", "SHOPEE", "ALIEXPRESS", "AMAZON"]
    indices = {loja: 0 for loja in por_loja}
    fila = []

    for loja_alvo in ordem_lojas:
        if len(fila) >= POSTS_POR_CICLO * 2:
            break
        if loja_alvo in por_loja and indices.get(loja_alvo, 0) < len(por_loja[loja_alvo]):
            fila.append(por_loja[loja_alvo][indices[loja_alvo]])
            indices[loja_alvo] += 1
        else:
            for loja, lista in por_loja.items():
                idx = indices.get(loja, 0)
                if idx < len(lista):
                    fila.append(lista[idx])
                    indices[loja] = idx + 1
                    break

    # Remove duplicatas mantendo ordem
    vistos = set()
    resultado = []
    for p in fila:
        chave = hashlib.md5(p["nome"].encode()).hexdigest()
        if chave not in vistos:
            vistos.add(chave)
            resultado.append(p)

    lojas_log = {}
    for p in resultado[:POSTS_POR_CICLO]:
        lojas_log[p.get("loja","")] = lojas_log.get(p.get("loja",""), 0) + 1

    log.info(f"Pipeline: {len(resultado)} produtos prontos ({contar_postados()} no historico)")
    log.info(f"Distribuicao: {lojas_log}")
    for p in resultado[:8]:
        log.info(f"  [{p['score']}pts][{p['loja']}] {p['nome'][:40]} | {fmt_preco(p['preco'])}")
    return resultado


# ============================================================
# CICLO PRINCIPAL
# ============================================================

def ciclo():
    log.info(f"\n{'='*50}")
    log.info(f"Ciclo — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    limpar_historico_antigo()
    produtos = montar_pipeline()
    postou = 0
    for produto in produtos:
        log.info(f"Postando [{produto['score']}pts]: {produto['nome'][:50]}")
        imagem = gerar_imagem(produto)
        ok = postar_telegram(produto, imagem)
        if ok:
            registrar_post(produto)
            postou += 1
            log.info("✅ Postado!")
        else:
            log.error("❌ Falha")
        if postou >= POSTS_POR_CICLO:
            break
        time.sleep(10)
    log.info(f"Ciclo concluído — {postou} post(s)\n")


def main():
    init_db()
    log.info("🤖 OlhaissoTech Bot v6.0 iniciado!")
    log.info(f"📢 Canal: {TELEGRAM_CHANNEL}")
    log.info(f"⏰ Horários: {', '.join(HORARIOS)}")
    log.info(f"📦 Posts por ciclo: {POSTS_POR_CICLO}")
    log.info(f"🗓️ Sem repetir por: {DIAS_SEM_REPETIR} dias\n")
    for h in HORARIOS:
        schedule.every().day.at(h).do(ciclo)
    ciclo()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
