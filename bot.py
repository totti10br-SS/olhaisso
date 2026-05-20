"""
OlhaissoTech Bot v6.0
- AliExpress API oficial (AppKey: 530504)
- Shopee API oficial (AppID: 18307831002)
- Mercado Livre API pública (Publisher: ot20260326074822)
- Amazon Best Sellers
- Google Trends BR
- TikTok Creative Center
- Reddit gadgets
- Score inteligente por cruzamento de fontes
- Imagem 1080x1080 com logo
- SQLite para evitar repetição de produtos
"""

import os
import time
import hashlib
import logging
import sqlite3
import schedule
import re
import requests
import textwrap
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from aliexpress_api import buscar_todos_produtos as buscar_aliexpress
from aliexpress_api import buscar_ticket_baixo as buscar_aliexpress_tb
from shopee_api import buscar_todos_produtos as buscar_shopee
from shopee_api import buscar_ticket_baixo as buscar_shopee_tb
from amazon_api import buscar_todos_produtos as buscar_amazon
from amazon_api import buscar_imagem_amazon
from mercadolivre_api import buscar_todos_produtos as buscar_ml

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
ADMIN_CHAT_ID    = os.getenv("ADMIN_CHAT_ID", "")  # Seu chat ID pessoal para alertas

# Contador de falhas consecutivas do WhatsApp
_wa_falhas_consecutivas = 0
_WA_FALHAS_ALERTA = 3  # Alerta após 3 falhas seguidas
AMAZON_TAG       = os.getenv("AMAZON_TAG", "olhaissotech-20")
PRECO_MAXIMO     = float(os.getenv("PRECO_MAXIMO", "800"))
DESCONTO_MINIMO  = int(os.getenv("DESCONTO_MINIMO", "20"))
POSTS_POR_CICLO  = int(os.getenv("POSTS_POR_CICLO", "8"))
HORARIOS            = ["07:30", "10:00", "12:30", "15:00", "16:00", "17:30", "19:00", "20:30", "22:30", "01:00"]
HORARIOS_MISTO      = ["12:30", "20:30"]  # Ciclo misto: metade smartphones + metade monitores
HORARIOS_MONITOR    = ["15:00"]           # Ciclo dedicado apenas monitores
HORARIOS_ELETRO     = ["16:00"]           # Ciclo dedicado eletrodomésticos (ML + Amazon)
HORARIO_TICKET_BAIXO = ["19:00"]          # Ciclo dedicado produtos até R$200
HORARIO_COPA         = ["20:00"]           # 📺🇧🇷 Momento TVs para Copa 2026
PRECO_TICKET_BAIXO   = float(os.getenv("PRECO_TICKET_BAIXO", "200.0"))  # Teto para ticket baixo
POSTS_TICKET_BAIXO_NO_CICLO = 2          # Qtde de tickets baixos nos ciclos normais
DB_PATH          = os.getenv("DB_PATH", "/data/olhaissotech.db")

# Evolution API — WhatsApp
EVOLUTION_URL      = os.getenv("EVOLUTION_URL", "https://evolution-api-production-b1df.up.railway.app")
EVOLUTION_APIKEY   = os.getenv("EVOLUTION_APIKEY", "A05E4CD20532-4B74-BA78-7FC09B26F2B0")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "OlhaissOTech")
WHATSAPP_GROUP_ID      = os.getenv("WHATSAPP_GROUP_ID", "120363409953330235@g.us")
WHATSAPP_TEST_GROUP_ID = os.getenv("WHATSAPP_TEST_GROUP_ID", "120363426249897089@g.us")  # Grupo de testes — não usado ainda

# Quantos dias manter um produto no histórico antes de poder repetir
DIAS_SEM_REPETIR = int(os.getenv("DIAS_SEM_REPETIR", "2"))  # mantido por compatibilidade
HORAS_SEM_REPETIR = int(os.getenv("HORAS_SEM_REPETIR", str(DIAS_SEM_REPETIR * 24)))

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
            postado_em TEXT NOT NULL,
            origem    TEXT DEFAULT 'BOT'
        )
    """)
    # Migration: adiciona coluna origem se nao existir
    try:
        c.execute("ALTER TABLE postados ADD COLUMN origem TEXT DEFAULT 'BOT'")
        conn.commit()
        log.info("SQLite: coluna 'origem' adicionada")
    except Exception:
        pass  # coluna ja existe
    # Migration: adiciona coluna link se nao existir
    try:
        c.execute("ALTER TABLE postados ADD COLUMN link TEXT DEFAULT ''")
        conn.commit()
        log.info("SQLite: coluna 'link' adicionada")
    except Exception:
        pass  # coluna ja existe
    conn.commit()
    conn.close()
    log.info(f"SQLite iniciado: {DB_PATH}")


def ja_postado(hash_produto):
    """Verifica se produto foi postado nas últimas HORAS_SEM_REPETIR horas."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        limite = (datetime.now() - timedelta(hours=HORAS_SEM_REPETIR)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT id FROM postados WHERE hash = ? AND postado_em > ?", (hash_produto, limite))
        resultado = c.fetchone()
        conn.close()
        return resultado is not None
    except Exception as e:
        log.error(f"SQLite erro ao verificar: {e}")
        return False


def registrar_post(produto, origem="BOT"):
    """Registra produto postado no banco."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        hash_p = hashlib.md5(produto["nome"].encode()).hexdigest()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        link = produto.get("link_afiliado", "")
        c.execute("""
            INSERT OR REPLACE INTO postados (hash, nome, preco, loja, postado_em, origem, link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (hash_p, produto["nome"][:200], produto.get("preco", 0),
              produto.get("loja", ""), agora, origem, link))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"SQLite erro ao registrar: {e}")


def limpar_historico_antigo():
    """Remove registros mais antigos que HORAS_SEM_REPETIR * 2 horas."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        limite = (datetime.now() - timedelta(hours=HORAS_SEM_REPETIR * 2)).strftime("%Y-%m-%d %H:%M:%S")
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


def badge_score(score, ticket_baixo=False, copa_2026=False):
    if ticket_baixo:
        return ("🤑 BOM e BARATO", COR_VERDE)
    if copa_2026:
        return ("📺🇧🇷⚽ COPA 2026", (0, 156, 59))
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

    # ── TOPO: badge único grande centralizado ──────────────────
    label_score, cor_score = badge_score(produto.get("score", 0), produto.get("ticket_baixo", False), produto.get("copa_2026", False))
    f_badge = carregar_fonte(54, negrito=True)
    bw, bh = 580, 90
    bx = (W - bw) // 2
    draw.rounded_rectangle([bx, 24, bx+bw, 24+bh], radius=45, fill=cor_score)
    bb = draw.textbbox((0,0), label_score, font=f_badge)
    draw.text((bx+(bw-(bb[2]-bb[0]))//2, 24+(bh-(bb[3]-bb[1]))//2), label_score, font=f_badge, fill=COR_BRANCO)

    # ── BADGES LOJA + DESCONTO lado a lado ────────────────────
    f_sub_badge = carregar_fonte(44, negrito=True)
    loja = produto.get("loja", "ALIEXPRESS")
    desc = produto.get("desconto", 0)

    # Badge loja (esquerda)
    draw.rounded_rectangle([50, 130, 50+300, 130+72], radius=36, fill=(40,40,40))
    bb2 = draw.textbbox((0,0), loja, font=f_sub_badge)
    draw.text((50+(300-(bb2[2]-bb2[0]))//2, 130+(72-(bb2[3]-bb2[1]))//2), loja, font=f_sub_badge, fill=COR_LARANJA)

    # Badge desconto (direita)
    if desc > 0:
        desc_txt = f"-{desc}% OFF"
        draw.rounded_rectangle([W-50-300, 130, W-50, 130+72], radius=36, fill=COR_VERDE)
        bb3 = draw.textbbox((0,0), desc_txt, font=f_sub_badge)
        draw.text((W-50-300+(300-(bb3[2]-bb3[0]))//2, 130+(72-(bb3[3]-bb3[1]))//2), desc_txt, font=f_sub_badge, fill=COR_BRANCO)

    # ── FOTO DO PRODUTO ────────────────────────────────────────
    img_url = produto.get("imagem_url", "")

    # Para Amazon: busca imagem agora (só para produtos que vão ser postados)
    if not img_url and produto.get("loja") == "AMAZON":
        try:
            img_url = buscar_imagem_amazon(produto)
            if img_url:
                produto["imagem_url"] = img_url  # salva no produto para uso posterior
        except Exception as e:
            log.warning(f"Amazon imagem on-demand erro: {e}")

    prod_img = None
    if img_url:
        try:
            r = requests.get(img_url, timeout=8)
            prod_img = Image.open(BytesIO(r.content)).convert("RGBA")
            prod_img = prod_img.resize((600, 460), Image.LANCZOS)
        except:
            prod_img = None

    if prod_img:
        img.paste(prod_img, ((W-600)//2, 215), prod_img)
    else:
        draw.rounded_rectangle([240, 215, 840, 675], radius=20, fill=COR_CINZA_ESCURO)
        f_ico = carregar_fonte(100)
        draw.text((540, 445), "📦", font=f_ico, fill=(70,70,70), anchor="mm")

    # ── ÁREA DE TEXTO: fundo escuro arredondado ────────────────
    draw.rounded_rectangle([32, 690, W-32, H-120], radius=28, fill=(22,22,22))

    y = 706

    # 👀 OlhaissO
    f_marca = carregar_fonte(50, negrito=True)
    marca_txt = "👀 OlhaissO"
    bb_m = draw.textbbox((0,0), marca_txt, font=f_marca)
    draw.text(((W-(bb_m[2]-bb_m[0]))//2, y), marca_txt, font=f_marca, fill=COR_LARANJA)
    y += 66

    # Nome do produto
    f_nome = carregar_fonte(48, negrito=True)
    nome = produto.get("nome", "")

    # Detecta se é Oferta Premium do Canal — banner especial
    PREFIXO_PREMIUM = "🏆 OFERTA PREMIUM DO CANAL"
    if nome.startswith(PREFIXO_PREMIUM):
        # Banner vermelho com texto azul negrito
        COR_VERMELHO    = (200, 20, 20)
        COR_AZUL_BRIGHT = (30, 120, 255)
        f_premium = carregar_fonte(46, negrito=True)
        banner_txt = "🏆 OFERTA PREMIUM DO CANAL"
        bb_p = draw.textbbox((0, 0), banner_txt, font=f_premium)
        bw_p = bb_p[2] - bb_p[0]
        bh_p = bb_p[3] - bb_p[1]
        pad_x, pad_y = 30, 12
        rx1 = (W - bw_p) // 2 - pad_x
        rx2 = (W + bw_p) // 2 + pad_x
        draw.rounded_rectangle([rx1, y, rx2, y + bh_p + pad_y * 2], radius=16, fill=COR_VERMELHO)
        draw.text(((W - bw_p) // 2, y + pad_y), banner_txt, font=f_premium, fill=COR_AZUL_BRIGHT)
        y += bh_p + pad_y * 2 + 10
        # Resto do nome sem o prefixo
        nome_real = nome[len(PREFIXO_PREMIUM):].strip().lstrip("\n").strip()
        linhas = textwrap.wrap(nome_real, width=32)[:2]
    else:
        linhas = textwrap.wrap(nome, width=32)[:2]

    for linha in linhas:
        bb = draw.textbbox((0,0), linha, font=f_nome)
        draw.text(((W-(bb[2]-bb[0]))//2, y), linha, font=f_nome, fill=COR_BRANCO)
        y += 60

    y += 8

    # Preço original riscado
    preco_orig = produto.get("preco_original", 0)
    preco = produto.get("preco", 0)
    if preco_orig > preco:
        f_old = carregar_fonte(40)
        txt_old = f"De {fmt_preco(preco_orig)}"
        bb = draw.textbbox((0,0), txt_old, font=f_old)
        tw = bb[2]-bb[0]
        x_old = (W-tw)//2
        draw.text((x_old, y), txt_old, font=f_old, fill=COR_CINZA)
        meio_y = y + (bb[3]-bb[1])//2
        draw.line([(x_old, meio_y), (x_old+tw, meio_y)], fill=COR_CINZA, width=2)
        y += 54

    # Preço atual — destaque máximo
    f_preco = carregar_fonte(88, negrito=True)
    txt_preco = fmt_preco(preco)
    bb = draw.textbbox((0,0), txt_preco, font=f_preco)
    draw.text(((W-(bb[2]-bb[0]))//2, y), txt_preco, font=f_preco, fill=COR_LARANJA)
    y += 96

    # Frete
    frete = produto.get("frete", "")
    if frete:
        f_frete = carregar_fonte(40)
        bb = draw.textbbox((0,0), frete, font=f_frete)
        draw.text(((W-(bb[2]-bb[0]))//2, y), frete, font=f_frete, fill=COR_VERDE)

    # ── RODAPÉ LARANJA ─────────────────────────────────────────
    draw.rounded_rectangle([32, H-108, W-32, H-28], radius=30, fill=COR_LARANJA)
    desenhar_logo(draw, 58, H-96, tamanho=32)
    f_cta = carregar_fonte(38, negrito=True)
    cta = "OlhaissoTech — Link na bio e no Telegram!"
    bb = draw.textbbox((0,0), cta, font=f_cta)
    draw.text(((W-(bb[2]-bb[0]))//2 + 20, H-84), cta, font=f_cta, fill=COR_BRANCO)

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

    eco = fmt_economia(orig, preco) if orig > preco else None

    # Badge de urgência por score
    if score >= 3:
        badge = "🔥 <b>VIRAL AGORA</b>"
    elif score == 2:
        badge = "📈 <b>TENDÊNCIA</b>"
    else:
        badge = "💰 <b>OFERTA DO DIA</b>"
    if produto.get("ticket_baixo", False):
        badge = "🤑 <b>Momento BOM e BARATO</b>"
    if produto.get("copa_2026", False):
        badge = "📺🇧🇷⚽ <b>MOMENTO TVS — COPA 2026!</b>"

    # Badge de loja
    loja_badge = {"ALIEXPRESS": "🛍️ AliExpress", "SHOPEE": "🧡 Shopee", "AMAZON": "📦 Amazon"}.get(loja, loja)

    txt  = f"👀 <b>OlhaissO</b> — {badge}\n"
    txt += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    txt += f"<b>{nome}</b>\n\n"

    if desc > 0:
        txt += f"🏷️ <b>{desc}% OFF</b>"
        if eco:
            txt += f"  |  Economia de <b>{eco}</b>"
        txt += "\n"

    txt += f"\n💵 De <s>{fmt_preco(orig)}</s> por apenas\n"
    txt += f"💰 <b>{fmt_preco(preco)}</b>\n\n"

    txt += f"{loja_badge}"
    if frete:
        txt += f"  •  {frete}"
    txt += "\n"

    if fontes:
        labels = {"google": "Google Trends", "tiktok": "TikTok", "reddit": "Reddit", "amazon": "Amazon", "aliexpress": "AliExpress", "shopee": "Shopee"}
        txt += f"📊 Em alta: {' · '.join([labels.get(f,f) for f in fontes])}\n"

    txt += f"\n🛒 <a href=\"{link}\"><b>COMPRAR AGORA — CLIQUE AQUI</b></a>\n"
    txt += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    txt += f"<i>👀 OlhaissoTech | Gadgets com o melhor preço</i>"
    return txt


def enviar_alerta_admin(mensagem):
    """Envia mensagem de alerta para o chat pessoal do admin via Telegram."""
    if not ADMIN_CHAT_ID or not TELEGRAM_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": mensagem, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        log.warning(f"Alerta admin falhou: {e}")


def checar_evolution():
    """Verifica se a Evolution API está respondendo antes de tentar postar."""
    if not EVOLUTION_URL:
        return False
    try:
        r = requests.get(
            f"{EVOLUTION_URL}/instance/fetchInstances",
            headers={"apikey": EVOLUTION_APIKEY},
            timeout=10
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


def postar_telegram(produto, imagem_path):
    caption = montar_caption(produto)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    img_url = produto.get("imagem_url", "")

    # Tenta 1: foto real do produto via URL
    if img_url:
        try:
            r = requests.post(url, data={
                "chat_id": TELEGRAM_CHANNEL,
                "photo": img_url,
                "caption": caption,
                "parse_mode": "HTML",
            }, timeout=30)
            if r.status_code == 200:
                return True
            log.warning(f"Imagem URL falhou ({r.status_code}), tentando imagem gerada...")
        except Exception as e:
            log.warning(f"Imagem URL exceção: {e}, tentando imagem gerada...")

    # Tenta 2: imagem gerada localmente (PIL)
    try:
        with open(imagem_path, "rb") as f:
            r = requests.post(url, data={
                "chat_id": TELEGRAM_CHANNEL,
                "caption": caption,
                "parse_mode": "HTML",
            }, files={"photo": f}, timeout=30)
        if r.status_code == 200:
            return True
        log.error(f"Telegram erro imagem gerada: {r.text[:200]}")
    except Exception as e:
        log.error(f"Telegram exceção imagem gerada: {e}")

    # Sem imagem = não publica, produto será registrado no banco e pulado
    log.warning(f"Produto pulado por falha de imagem: {produto.get('nome','')[:50]}")
    return False


def fazer_upload_imagem(imagem_path):
    """Faz upload da imagem gerada para imgbb e retorna URL pública."""
    IMGBB_KEY = os.getenv("IMGBB_KEY", "")
    if not IMGBB_KEY:
        log.warning("imgbb: IMGBB_KEY não configurada!")
        return None
    try:
        import base64
        with open(imagem_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        r = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_KEY, "image": img_b64},
            timeout=20
        )
        log.info(f"imgbb status: {r.status_code}")
        if r.status_code == 200:
            url = r.json()["data"]["url"]
            log.info(f"imgbb URL: {url}")
            return url
        log.warning(f"imgbb erro: {r.text[:200]}")
    except Exception as e:
        log.warning(f"imgbb upload falhou: {e}")
    return None


def postar_whatsapp(produto, imagem_path):
    """Posta no grupo WhatsApp via Evolution API. Com retry, timeout 60s e alerta ao admin."""
    global _wa_falhas_consecutivas
    if not EVOLUTION_URL or not WHATSAPP_GROUP_ID:
        return False

    try:
        nome    = produto.get("nome", "")
        preco   = produto.get("preco", 0)
        orig    = produto.get("preco_original", 0)
        desc    = produto.get("desconto", 0)
        link    = produto.get("link_afiliado", "")
        loja    = produto.get("loja", "")
        img_url = produto.get("imagem_url", "")

        loja_label = {"ALIEXPRESS": "🛍️ AliExpress", "SHOPEE": "🧡 Shopee", "AMAZON": "📦 Amazon"}.get(loja, loja)
        _sc = produto.get("score", 0)
        badge = "🤑 Momento BOM e BARATO" if produto.get("ticket_baixo", False) else ("🔥 VIRAL AGORA" if _sc >= 3 else "📈 TENDÊNCIA" if _sc == 2 else "💰 OFERTA DO DIA")

        def fmt(v):
            return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        # Caption limpo para WhatsApp — sem HTML
        texto  = f"👀 *OlhaissO* — {badge}\n"
        texto += f"━━━━━━━━━━━━━━━━━━━━\n\n"
        texto += f"*{nome}*\n\n"
        if desc > 0:
            eco = round(orig - preco, 2)
            texto += f"🏷️ *{desc}% OFF*  |  Economia de *{fmt(eco)}*\n"
        if orig > preco:
            texto += f"\n💵 De {fmt(orig)} por apenas\n"
        texto += f"💰 *{fmt(preco)}*\n\n"
        texto += f"{loja_label}\n"
        texto += f"\n🛒 *COMPRAR AGORA:*\n{link}\n"
        texto += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        texto += f"👀 OlhaissoTech | Gadgets com o melhor preço"

        headers = {
            "apikey": EVOLUTION_APIKEY,
            "Content-Type": "application/json",
        }

        # Tenta com imagem via URL do produto
        if img_url:
            payload = {
                "number": WHATSAPP_GROUP_ID,
                "mediatype": "image",
                "mimetype": "image/jpeg",
                "caption": texto,
                "media": img_url,
            }
            # Tenta com imagem — até 2 tentativas com timeout 60s
            for tentativa in range(2):
                try:
                    r = requests.post(
                        f"{EVOLUTION_URL}/message/sendMedia/{EVOLUTION_INSTANCE}",
                        json=payload, headers=headers, timeout=60
                    )
                    if r.status_code in (200, 201):
                        log.info("✅ WhatsApp postado com imagem!")
                        _wa_falhas_consecutivas = 0
                        return True
                    log.warning(f"WhatsApp imagem falhou ({r.status_code}) tentativa {tentativa+1}")
                except Exception as e:
                    log.warning(f"WhatsApp imagem exceção tentativa {tentativa+1}: {e}")
                if tentativa == 0:
                    time.sleep(5)

        # Fallback: posta só o texto sem imagem — até 3 tentativas
        payload_txt = {
            "number": WHATSAPP_GROUP_ID,
            "text": texto,
        }
        for tentativa in range(3):
            try:
                r = requests.post(
                    f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
                    json=payload_txt, headers=headers, timeout=60
                )
                if r.status_code in (200, 201):
                    log.info("✅ WhatsApp postado (só texto)!")
                    _wa_falhas_consecutivas = 0
                    return True
                log.warning(f"WhatsApp texto falhou ({r.status_code}) tentativa {tentativa+1}: {r.text[:100]}")
            except Exception as e:
                log.warning(f"WhatsApp texto exceção tentativa {tentativa+1}: {e}")
            if tentativa < 2:
                time.sleep(10)

        # Todas as tentativas falharam
        _wa_falhas_consecutivas += 1
        log.error(f"❌ WhatsApp falhou após todas tentativas ({_wa_falhas_consecutivas} ciclos consecutivos)")
        if _wa_falhas_consecutivas >= _WA_FALHAS_ALERTA:
            enviar_alerta_admin(
                f"⚠️ <b>OlhaissoTech — WhatsApp com problemas!</b>\n\n"
                f"O WhatsApp falhou em <b>{_wa_falhas_consecutivas}</b> ciclos consecutivos.\n"
                f"Verifique a Evolution API no Railway.\n\n"
                f"Último produto: {produto.get('nome','?')[:50]}"
            )
        return False

    except Exception as e:
        log.warning(f"WhatsApp exceção geral: {e}")
        _wa_falhas_consecutivas += 1
        return False

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



KEYWORDS_SMARTPHONE = [
    "smartphone", "telefone", "celular", "iphone", "samsung galaxy",
    "redmi", "poco", "motorola moto", "realme", "xiaomi mi",
]

MAX_POR_TEMA = int(os.getenv("MAX_POR_TEMA", "2"))

TEMAS = [
    ("smartphone",   ["smartphone", "celular", "iphone", "redmi", "poco", "motorola moto", "realme", "samsung galaxy"]),
    ("notebook",     ["notebook", "laptop"]),
    ("fone",         ["fone", "earbuds", "earphone", "headset", "headphone", "auricular", "fone de ouvido"]),
    ("smartwatch",   ["smartwatch", "smart watch", "relogio inteligente", "band ", "relógio inteligente"]),
    ("carregador",   ["carregador", "power bank", "powerbank", "gan charger", "carregador rapido"]),
    ("mouse",        ["mouse gamer", "mouse sem fio", "mouse wireless", "gaming mouse"]),
    ("teclado",      ["teclado", "keyboard"]),
    ("caixa de som", ["caixa de som", "bluetooth speaker", "speaker portátil", "speaker portatil",
                      "caixinha bluetooth", "caixinha de som", "som bluetooth", "speaker bluetooth",
                      "caixa bluetooth", "jbl speaker", "jbl flip", "jbl charge", "jbl go",
                      "portable speaker", "alto-falante", "alto falante"]),
    ("monitor",      ["monitor "]),
    ("tv",           ["smart tv", "tv 4k", "tv qled", "tv oled", "televisão", "televisao"]),
    ("videogame",    ["playstation", "xbox", "nintendo switch", "ps5", "ps4", "game console", "video game"]),
    ("aspirador",    ["aspirador", "robot vacuum", "robo aspirador"]),
    ("fritadeira",   ["fritadeira", "air fryer", "airfryer"]),
    ("projetor",     ["projetor", "projector"]),
    ("hub usb",      ["hub usb", "docking station"]),
    ("ssd",          ["ssd", "nvme", "m.2", "hd externo", "pendrive", "pen drive", "armazenamento"]),
    ("webcam",       ["webcam"]),
    ("led",          ["fita led", "led strip", "luminaria", "lampada"]),
    ("ram",          ["memoria ram", "ram ddr", "ddr4", "ddr5", "ddr3", "ram 4gb", "ram 8gb",
                      "ram 16gb", "ram 32gb", "memory ram", "memória ddr"]),
    ("processador",  ["processador", "processor", "intel core", "amd ryzen", "xeon", "cpu"]),
    ("placa mae",    ["placa-mae", "placa mae", "motherboard", "placa mãe"]),
    ("placa video",  ["placa grafica", "placa gráfica", "gpu", "geforce", "radeon", "rx580",
                      "rtx ", "gtx ", "rx 580", "rx 570", "vga card", "graphics card"]),
    ("cooler",       ["cooler", "ventoinha", "fan cooler", "cpu cooler", "water cooler"]),
    ("cabo",         ["cabo usb", "cabo tipo c", "cabo hdmi", "cabo lightning"]),
    ("microscopio",  ["microscopio", "microscópio", "lupa", "telescopio", "telescópio",
                      "estetoscopio", "termometro clinico"]),
    ("movel",        ["sofa", "sofá", "colchao", "colchão", "travesseiro", "edredom",
                      "cortina", "tapete", "guarda-roupa", "armario"]),
    ("vestuario",    ["camisa", "camiseta", "calca", "vestido", "sapato", "sandalia",
                      "tenis", "bota", "chinelo", "bolsa", "carteira", "perfume"]),
    ("saude",        ["suplemento", "creatina", "whey", "vitamina", "remedio",
                      "medicamento", "shampoo", "condicionador", "sabonete"]),
    ("jardim",       ["cortador de grama", "vaso de planta", "mangueira", "regador",
                      "churrasqueira", "fogao a lenha"]),
]

def hora_atual_str():
    return datetime.now().strftime("%H:%M")

def horario_dentro_de(horarios, tolerancia_min=30):
    """Verifica se a hora atual está dentro da tolerância de algum horário da lista."""
    agora = datetime.now()
    for h in horarios:
        hh, mm = map(int, h.split(":"))
        alvo = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)
        diff = abs((agora - alvo).total_seconds() / 60)
        if diff <= tolerancia_min:
            return True
    return False

def permitir_misto():
    return horario_dentro_de(HORARIOS_MISTO)

def permitir_monitor_dedicado():
    return horario_dentro_de(HORARIOS_MONITOR)

def permitir_eletro_dedicado():
    return horario_dentro_de(HORARIOS_ELETRO)

KEYWORDS_ELETRO = [
    "geladeira", "refrigerador", "fogão", "fogao", "micro-ondas", "microondas",
    "máquina de lavar", "maquina de lavar", "lava e seca", "secadora",
    "ar condicionado", "ventilador", "liquidificador", "batedeira", "mixer",
    "sanduicheira", "grill", "fritadeira", "airfryer", "air fryer",
    "panela elétrica", "panela eletrica", "cafeteira", "torradeira",
    "aspirador", "ferro de passar", "purificador", "aquecedor",
    "churrasqueira elétrica", "forno elétrico", "forno eletrico",
    "processador de alimentos", "espremedor",
]

KEYWORDS_TV = [
    "smart tv", "tv 4k", "tv qled", "tv oled", "tv mini led", "tv mini-led",
    "televisao", "televisao", "televisão",
    "tv 32", "tv 37", "tv 40", "tv 43", "tv 50", "tv 55", "tv 65", "tv 75", "tv 85",
    "43 polegadas", "50 polegadas", "55 polegadas", "65 polegadas", "75 polegadas", "85 polegadas",
    "qled 4k", "oled 4k", "led 4k", "mini led 4k",
    "tv samsung", "tv lg", "tv sony", "tv tcl", "tv philips", "tv aoc", "tv hisense",
    "android tv", "google tv", "roku tv", "fire tv",
]

DESCONTO_MINIMO_TV = 30  # Desconto minimo para o ciclo Copa

KEYWORDS_MONITOR = [
    "monitor ", "monitor gamer", "monitor 4k", "monitor ips",
    "monitor curvo", "monitor portatil", "monitor led",
    "monitor 144hz", "monitor 165hz", "monitor 240hz",
    "tela monitor", "display monitor",
]

def distribuir_por_loja(pool_ml, pool_ali, pool_shopee, pool_amazon, pool_outros, total):
    """Monta fila com distribuição 40% ML, 40% Amazon, 10% Ali, 10% Shopee."""
    qtd_ml     = max(1, round(total * 0.40))
    qtd_amazon = max(1, round(total * 0.40))
    qtd_ali    = max(1, round(total * 0.10))
    qtd_shopee = max(1, total - qtd_ml - qtd_amazon - qtd_ali)
    log.info(f"Distribuição alvo: {qtd_ml} ML | {qtd_amazon} Amazon | {qtd_ali} Ali | {qtd_shopee} Shopee")
    fila = []
    fila += pool_ml[:qtd_ml]
    fila += pool_amazon[:qtd_amazon]
    fila += pool_ali[:qtd_ali]
    fila += pool_shopee[:qtd_shopee]
    # Completa com extras se faltar
    extras = pool_ml[qtd_ml:] + pool_amazon[qtd_amazon:] + pool_ali[qtd_ali:] + pool_shopee[qtd_shopee:] + pool_outros
    for p in extras:
        if len(fila) >= total * 2:
            break
        fila.append(p)
    return fila


def _is_smartphone(nome):
    return any(kw in nome.lower() for kw in KEYWORDS_SMARTPHONE)

def _is_monitor(nome):
    return any(kw in nome.lower() for kw in KEYWORDS_MONITOR)

def _is_eletro(nome):
    return any(kw in nome.lower() for kw in KEYWORDS_ELETRO)

def _is_tv(nome):
    return any(kw in nome.lower() for kw in KEYWORDS_TV)

def permitir_copa():
    return horario_dentro_de(HORARIO_COPA)


def montar_ciclo_eletro(pool_ml, pool_ali, pool_shopee, pool_amazon, pool_outros):
    """Ciclo 16:00 — apenas eletrodomésticos de ML e Amazon, sem Ali/Shopee."""
    log.info("🏠 CICLO ELETRO — apenas Eletrodomésticos (ML + Amazon)")
    ml_el  = [p for p in pool_ml     if _is_eletro(p.get("nome", ""))]
    az_el  = [p for p in pool_amazon if _is_eletro(p.get("nome", ""))]
    total  = len(ml_el) + len(az_el)
    log.info(f"🏠 {total} eletrodoméstico(s) disponíveis (ML:{len(ml_el)} Amazon:{len(az_el)})")
    # Distribuição 50/50 entre ML e Amazon
    qtd_cada = max(1, POSTS_POR_CICLO // 2)
    fila = ml_el[:qtd_cada] + az_el[:qtd_cada]
    # Completa se faltar
    extras = ml_el[qtd_cada:] + az_el[qtd_cada:]
    for p in extras:
        if len(fila) >= POSTS_POR_CICLO * 2:
            break
        fila.append(p)
    return fila


def montar_ciclo_copa(pool_ml, pool_amazon):
    """📺🇧🇷 Ciclo 20:00 — Momento TVs para Copa 2026. 5 Amazon + 5 ML. Desconto >= 30%."""
    log.info("📺🇧🇷⚽ CICLO COPA 2026 — Momento TVs!")

    def filtrar_tvs(pool):
        return [
            p for p in pool
            if _is_tv(p.get("nome", ""))
            and p.get("desconto", 0) >= DESCONTO_MINIMO_TV
        ]

    tvs_ml     = filtrar_tvs(pool_ml)
    tvs_amazon = filtrar_tvs(pool_amazon)
    log.info(f"📺 TVs encontradas: ML={len(tvs_ml)} | Amazon={len(tvs_amazon)}")

    fila = tvs_amazon[:5] + tvs_ml[:5]
    extras = tvs_amazon[5:] + tvs_ml[5:]
    for p in extras:
        if len(fila) >= 10:
            break
        fila.append(p)

    for p in fila:
        p["copa_2026"] = True

    log.info(f"📺🇧🇷 {len(fila)} TV(s) prontas para o ciclo Copa")
    return fila


def permitir_ciclo_ticket_baixo():
    return horario_dentro_de(HORARIO_TICKET_BAIXO)

def eh_ticket_baixo(produto):
    return produto.get("preco", 999) <= PRECO_TICKET_BAIXO


def montar_pipeline_ticket_baixo():
    """Pipeline dedicado para ciclo das 19:00 — busca apenas produtos até R$200."""
    log.info(f"💰 PIPELINE TICKET BAIXO — buscando produtos até R${PRECO_TICKET_BAIXO:.0f}")

    log.info("💰 Buscando AliExpress ticket baixo...")
    ali_tb = buscar_aliexpress_tb()

    log.info("💰 Buscando Shopee ticket baixo...")
    sh_tb = buscar_shopee_tb()

    todos = ali_tb + sh_tb
    log.info(f"💰 Total bruto: {len(todos)} (Ali:{len(ali_tb)} Sh:{len(sh_tb)})")

    # Remove já postados
    vistos = set()
    resultado = []
    for p in todos:
        chave = hashlib.md5(p["nome"].encode()).hexdigest()
        if chave not in vistos and not ja_postado(chave):
            vistos.add(chave)
            p["ticket_baixo"] = True
            resultado.append(p)

    # Ordena por desconto
    resultado.sort(key=lambda x: x.get("desconto", 0), reverse=True)
    log.info(f"💰 Prontos para postar: {len(resultado)} produtos ticket baixo")
    return resultado


def montar_ciclo_ticket_baixo(pool_ml, pool_ali, pool_shopee, pool_outros):
    """Ciclo 19:00 — delega para pipeline dedicado."""
    return []  # não usado mais, ver ciclo()


def montar_ciclo_misto(pool_ml, pool_ali, pool_shopee, pool_outros, pool_amazon=None):
    """
    Ciclo misto (12:30 e 20:30): metade smartphones + metade monitores.
    Proporção 40% ML, 40% Amazon, 10% Ali, 10% Shopee por categoria.
    """
    if pool_amazon is None:
        pool_amazon = []
    metade = POSTS_POR_CICLO // 2

    # Separa por categoria
    def split_cat(pool):
        phones  = [p for p in pool if _is_smartphone(p.get("nome",""))]
        monitors= [p for p in pool if _is_monitor(p.get("nome",""))]
        outros  = [p for p in pool if not _is_smartphone(p.get("nome","")) and not _is_monitor(p.get("nome",""))]
        return phones, monitors, outros

    ml_ph,  ml_mo,  ml_ot  = split_cat(pool_ml)
    ali_ph, ali_mo, ali_ot = split_cat(pool_ali)
    sh_ph,  sh_mo,  sh_ot  = split_cat(pool_shopee)
    az_ph,  az_mo,  az_ot  = split_cat(pool_amazon)

    log.info(f"🔀 CICLO MISTO — alvo: {metade} smartphone(s) + {metade} monitor(es) | 40/40/10/10")

    # Smartphones com proporção 40% ML / 40% Amazon / 10% Ali / 10% Shopee
    qtd_ml_ph  = max(0, round(metade * 0.40))
    qtd_az_ph  = max(0, round(metade * 0.40))
    qtd_ali_ph = max(0, round(metade * 0.10))
    qtd_sh_ph  = max(0, metade - qtd_ml_ph - qtd_az_ph - qtd_ali_ph)
    smartphones = ml_ph[:qtd_ml_ph] + az_ph[:qtd_az_ph] + ali_ph[:qtd_ali_ph] + sh_ph[:qtd_sh_ph]
    # Completa se alguma loja não tiver suficiente (fallback nas extras)
    extras_ph = az_ph[qtd_az_ph:] + ml_ph[qtd_ml_ph:] + ali_ph[qtd_ali_ph:] + sh_ph[qtd_sh_ph:]
    smartphones += extras_ph[:max(0, metade - len(smartphones))]

    # Monitores com proporção 40% ML / 40% Amazon / 10% Ali / 10% Shopee
    qtd_ml_mo  = max(0, round(metade * 0.40))
    qtd_az_mo  = max(0, round(metade * 0.40))
    qtd_ali_mo = max(0, round(metade * 0.10))
    qtd_sh_mo  = max(0, metade - qtd_ml_mo - qtd_az_mo - qtd_ali_mo)
    monitores = ml_mo[:qtd_ml_mo] + az_mo[:qtd_az_mo] + ali_mo[:qtd_ali_mo] + sh_mo[:qtd_sh_mo]
    extras_mo = az_mo[qtd_az_mo:] + ml_mo[qtd_ml_mo:] + ali_mo[qtd_ali_mo:] + sh_mo[qtd_sh_mo:]
    monitores += extras_mo[:max(0, metade - len(monitores))]

    resultado = smartphones + monitores
    faltando = POSTS_POR_CICLO - len(resultado)
    if faltando > 0:
        extras = az_ot + ml_ot + ali_ot + sh_ot + pool_outros
        resultado += extras[:faltando]
        log.info(f"   Completado com {min(faltando, len(extras))} produto(s) genérico(s)")

    log.info(f"   {len(smartphones)} smartphone(s) | {len(monitores)} monitor(es) (ML:{qtd_ml_ph}/{qtd_ml_mo} Az:{qtd_az_ph}/{qtd_az_mo} Ali:{qtd_ali_ph}/{qtd_ali_mo} Sh:{qtd_sh_ph}/{qtd_sh_mo})")
    return resultado


def filtrar_ciclo_especial(pool_ml, pool_ali, pool_shopee, pool_amazon, pool_outros):
    """
    Recebe pools separados por loja e retorna lista filtrada por tipo de ciclo,
    mantendo proporção 40% ML / 40% Amazon / 10% Ali / 10% Shopee em todos os ciclos.
    """
    if permitir_copa():
        return montar_ciclo_copa(pool_ml, pool_amazon)

    if permitir_misto():
        return montar_ciclo_misto(pool_ml, pool_ali, pool_shopee, pool_outros, pool_amazon)

    if permitir_monitor_dedicado():
        log.info("🖥️ CICLO DEDICADO — apenas Monitores (40% ML / 40% Amazon / 10% Ali / 10% Shopee)")
        ml_mo  = [p for p in pool_ml     if _is_monitor(p.get("nome",""))]
        ali_mo = [p for p in pool_ali    if _is_monitor(p.get("nome",""))]
        sh_mo  = [p for p in pool_shopee if _is_monitor(p.get("nome",""))]
        az_mo  = [p for p in pool_amazon if _is_monitor(p.get("nome",""))]
        total  = len(ml_mo) + len(ali_mo) + len(sh_mo) + len(az_mo)
        log.info(f"🖥️ {total} monitor(es) disponíveis (ML:{len(ml_mo)} Amazon:{len(az_mo)} Ali:{len(ali_mo)} Sh:{len(sh_mo)})")
        return distribuir_por_loja(ml_mo, ali_mo, sh_mo, az_mo, [], POSTS_POR_CICLO)

    if permitir_eletro_dedicado():
        return montar_ciclo_eletro(pool_ml, pool_ali, pool_shopee, pool_amazon, pool_outros)

    if permitir_ciclo_ticket_baixo():
        return montar_ciclo_ticket_baixo(pool_ml, pool_ali, pool_shopee, pool_outros)

    # Ciclo normal — remove smartphones e monitores
    def filtrar_normal(pool):
        return [p for p in pool if not _is_smartphone(p.get("nome","")) and not _is_monitor(p.get("nome",""))]

    ml_n  = filtrar_normal(pool_ml)
    ali_n = filtrar_normal(pool_ali)
    sh_n  = filtrar_normal(pool_shopee)
    az_n  = filtrar_normal(pool_amazon)
    removidos = (len(pool_ml) - len(ml_n)) + (len(pool_ali) - len(ali_n)) + (len(pool_shopee) - len(sh_n)) + (len(pool_amazon) - len(az_n))
    if removidos > 0:
        log.info(f"🔒 {removidos} produto(s) reservados para ciclos especiais")

    # Ciclo normal: garante 2 tickets baixos na fila
    todos_normal = distribuir_por_loja(ml_n, ali_n, sh_n, az_n, pool_outros, POSTS_POR_CICLO * 3)
    tickets_baixos = [p for p in todos_normal if eh_ticket_baixo(p)][:POSTS_TICKET_BAIXO_NO_CICLO]
    for p in tickets_baixos:
        p["ticket_baixo"] = True
    tickets_altos  = [p for p in todos_normal if not eh_ticket_baixo(p)]
    resultado = tickets_baixos + tickets_altos
    if tickets_baixos:
        log.info(f"💰 {len(tickets_baixos)} produto(s) ticket baixo incluídos no ciclo normal")
    return resultado[:POSTS_POR_CICLO * 2]

def detectar_tema(nome):
    nome_lower = nome.lower()
    for tema, keywords in TEMAS:
        if any(kw in nome_lower for kw in keywords):
            return tema
    return "outros"

def limitar_por_tema(produtos):
    """Limita MAX_POR_TEMA produtos por tema no ciclo."""
    contagem = {}
    resultado = []
    pulados = []
    for p in produtos:
        tema = detectar_tema(p.get("nome", ""))
        count = contagem.get(tema, 0)
        if count < MAX_POR_TEMA:
            contagem[tema] = count + 1
            resultado.append(p)
        else:
            pulados.append(tema)
    if pulados:
        log.info(f"🎯 Limite por tema ({MAX_POR_TEMA}/tema): {len(pulados)} removido(s) — {', '.join(set(pulados))}")
    return resultado

def montar_pipeline(usar_ml=True, usar_shopee=True, usar_ali=True, usar_amazon=True):
    log.info("=== Pipeline v6.0 iniciado ===")
    tg = buscar_trends_google()
    tt = buscar_tiktok_trending()
    tr = buscar_reddit_gadgets()
    log.info(f"Tendências — Google: {len(tg)} | TikTok: {len(tt)} | Reddit: {len(tr)}")

    produtos_ali = []
    if usar_ali:
        log.info("Buscando AliExpress API...")
        produtos_ali = buscar_aliexpress()
    else:
        log.info("AliExpress ignorado (não selecionado)")

    produtos_shopee = []
    if usar_shopee:
        log.info("Buscando Shopee API...")
        produtos_shopee = buscar_shopee()
    else:
        log.info("Shopee ignorada (não selecionada)")

    produtos_ml = []
    if usar_ml:
        log.info("Buscando Mercado Livre...")
        produtos_ml = buscar_ml()
    else:
        log.info("Mercado Livre ignorado (não selecionado)")

    produtos_amazon = []
    if usar_amazon:
        log.info("Buscando Amazon Best Sellers...")
        produtos_amazon = buscar_amazon()
    else:
        log.info("Amazon ignorada (não selecionada)")

    # Aplica score em todos
    todos_raw = produtos_ali + produtos_shopee + produtos_ml + produtos_amazon
    for p in todos_raw:
        calcular_score(p, tg, tt, tr)

    if not todos_raw:
        log.warning("Sem produtos — usando mock")
        todos_raw = produtos_mock()

    # Filtra por preço e desconto
    todos_raw = [p for p in todos_raw if p.get("preco", 999) <= PRECO_MAXIMO and p.get("desconto", 0) >= DESCONTO_MINIMO]

    # Remove já postados (ML incluído no SQLite)
    antes = len(todos_raw)
    todos_raw = [p for p in todos_raw if not ja_postado(hashlib.md5(p["nome"].encode()).hexdigest())]
    filtrados = antes - len(todos_raw)
    if filtrados > 0:
        log.info(f"SQLite: {filtrados} produtos já postados recentemente removidos")

    # Separa por fonte e ordena por score ANTES do filtro de ciclo
    def filtrar_fonte(lista, loja):
        return sorted([p for p in lista if p.get("loja") == loja], key=lambda x: x.get("score", 0), reverse=True)

    pool_ml     = filtrar_fonte(todos_raw, "MERCADOLIVRE")
    pool_ali    = filtrar_fonte(todos_raw, "ALIEXPRESS")
    pool_shopee = filtrar_fonte(todos_raw, "SHOPEE")
    pool_amazon = filtrar_fonte(todos_raw, "AMAZON")
    pool_outros = [p for p in todos_raw if p.get("loja") not in ("MERCADOLIVRE", "ALIEXPRESS", "SHOPEE", "AMAZON")]

    # Filtra/organiza por ciclo especial mantendo proporção 40% ML / 40% Amazon / 10% Ali / 10% Shopee
    fila = filtrar_ciclo_especial(pool_ml, pool_ali, pool_shopee, pool_amazon, pool_outros)

    # Remove duplicatas mantendo ordem
    vistos = set()
    resultado = []
    for p in fila:
        chave = hashlib.md5(p["nome"].encode()).hexdigest()
        if chave not in vistos:
            vistos.add(chave)
            resultado.append(p)

    # Limita MAX_POR_TEMA produtos por tema no ciclo
    resultado = limitar_por_tema(resultado)

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

    # Health check da Evolution API antes de iniciar
    if EVOLUTION_URL:
        evolution_ok = checar_evolution()
        if not evolution_ok:
            log.warning("⚠️ Evolution API não responde — WhatsApp pode falhar neste ciclo")
            enviar_alerta_admin(
                f"⚠️ <b>OlhaissoTech — Evolution API offline!</b>\n\n"
                f"A Evolution API não respondeu ao health check antes do ciclo de "
                f"{datetime.now().strftime('%H:%M')}.\n"
                f"Posts serão feitos só no Telegram até reconectar."
            )
        else:
            log.info("✅ Evolution API OK")
    if permitir_ciclo_ticket_baixo():
        produtos = montar_pipeline_ticket_baixo()
    else:
        produtos = montar_pipeline()
    postou = 0
    tentativas = 0
    max_tentativas = 3  # tenta até 3 vezes buscar mais produtos se faltar

    while postou < POSTS_POR_CICLO and tentativas < max_tentativas:
        if not produtos:
            tentativas += 1
            if tentativas < max_tentativas:
                log.warning(f"Sem produtos disponíveis, buscando novamente (tentativa {tentativas})...")
                produtos = montar_pipeline()
                continue
            else:
                log.warning("Sem produtos suficientes após 3 tentativas.")
                break

        produto = produtos.pop(0)
        log.info(f"Postando [{produto['score']}pts]: {produto['nome'][:50]}")
        imagem = gerar_imagem(produto)
        ok_tg = postar_telegram(produto, imagem)
        if ok_tg:
            log.info("✅ Telegram OK")
            ok_wa = postar_whatsapp(produto, imagem)
            if ok_wa:
                # WhatsApp OK — registra normalmente
                registrar_post(produto)
                postou += 1
                log.info("✅ Postado! (Telegram + WhatsApp)")
            else:
                # WhatsApp falhou — NÃO registra para poder repostar depois
                log.warning("⚠️ WhatsApp falhou — produto NÃO registrado no banco (será repostado)")
                postou += 1  # conta como postado para não travar o ciclo
        else:
            registrar_post(produto)
            log.warning("⏭️ Telegram falhou — registrado para evitar retry infinito")
        time.sleep(10)

    log.info(f"Ciclo concluído — {postou} post(s)\n")


def postar_whatsapp_teste(produto, imagem_path):
    """Posta 1 oferta no grupo de teste via Evolution API."""
    if not EVOLUTION_URL or not WHATSAPP_TEST_GROUP_ID:
        log.warning("WhatsApp teste: WHATSAPP_TEST_GROUP_ID não configurado")
        return

    try:
        nome    = produto.get("nome", "")
        preco   = produto.get("preco", 0)
        orig    = produto.get("preco_original", 0)
        desc    = produto.get("desconto", 0)
        link    = produto.get("link_afiliado", "")
        loja    = produto.get("loja", "")
        img_url = produto.get("imagem_url", "")

        loja_label = {"ALIEXPRESS": "🛍️ AliExpress", "SHOPEE": "🧡 Shopee", "MERCADOLIVRE": "🟡 Mercado Livre", "AMAZON": "📦 Amazon"}.get(loja, loja)

        def fmt(v):
            return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        texto  = f"🧪 *[TESTE]* — OlhaissO Tech\n"
        texto += f"━━━━━━━━━━━━━━━━━━━━\n\n"
        texto += f"*{nome}*\n\n"
        if desc > 0:
            eco = round(orig - preco, 2)
            texto += f"🏷️ *{desc}% OFF*  |  Economia de *{fmt(eco)}*\n"
        if orig > preco:
            texto += f"\n💵 De {fmt(orig)} por apenas\n"
        texto += f"💰 *{fmt(preco)}*\n\n"
        texto += f"{loja_label}\n"
        texto += f"\n🛒 *COMPRAR AGORA:*\n{link}\n"
        texto += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        texto += f"🧪 Mensagem de teste — OlhaissoTech"

        headers = {
            "apikey": EVOLUTION_APIKEY,
            "Content-Type": "application/json",
        }

        if img_url:
            payload = {
                "number": WHATSAPP_TEST_GROUP_ID,
                "mediatype": "image",
                "mimetype": "image/jpeg",
                "caption": texto,
                "media": img_url,
            }
            r = requests.post(
                f"{EVOLUTION_URL}/message/sendMedia/{EVOLUTION_INSTANCE}",
                json=payload, headers=headers, timeout=30
            )
            if r.status_code in (200, 201):
                log.info("✅ WhatsApp TESTE postado com imagem!")
                return

        payload_txt = {
            "number": WHATSAPP_TEST_GROUP_ID,
            "text": texto,
        }
        requests.post(
            f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            json=payload_txt, headers=headers, timeout=30
        )
        log.info("✅ WhatsApp TESTE postado!")
    except Exception as e:
        log.error(f"WhatsApp teste erro: {e}")


def postar_whatsapp_custom(produto, imagem_path, group_id):
    """Posta no WhatsApp em grupo específico."""
    if not EVOLUTION_URL or not group_id:
        return
    try:
        nome  = produto.get("nome", "")
        preco = produto.get("preco", 0)
        orig  = produto.get("preco_original", 0)
        desc  = produto.get("desconto", 0)
        link  = produto.get("link_afiliado", "")
        loja  = produto.get("loja", "")
        img_url = produto.get("imagem_url", "")
        loja_label = {"ALIEXPRESS": "🛍️ AliExpress", "SHOPEE": "🧡 Shopee",
                      "AMAZON": "📦 Amazon", "MERCADOLIVRE": "🟡 Mercado Livre"}.get(loja, loja)
        _sc = produto.get("score", 0)
        badge = "🤑 Momento BOM e BARATO" if produto.get("ticket_baixo", False) else ("🔥 VIRAL AGORA" if _sc >= 3 else "📈 TENDÊNCIA" if _sc == 2 else "💰 OFERTA DO DIA")
        def fmt(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        texto  = f"👀 *OlhaissO* — {badge}\n"
        texto += f"━━━━━━━━━━━━━━━━━━━━\n\n"
        texto += f"*{nome}*\n\n"
        if desc > 0:
            eco = round(orig - preco, 2)
            texto += f"🏷️ *{desc}% OFF*  |  Economia de *{fmt(eco)}*\n"
        if orig > preco:
            texto += f"\n💵 De {fmt(orig)} por apenas\n"
        texto += f"💰 *{fmt(preco)}*\n\n"
        texto += f"{loja_label}\n"
        texto += f"\n🛒 *COMPRAR AGORA:*\n{link}\n"
        texto += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        texto += f"👀 OlhaissoTech | Gadgets com o melhor preço"
        headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
        if img_url:
            r = requests.post(
                f"{EVOLUTION_URL}/message/sendMedia/{EVOLUTION_INSTANCE}",
                json={"number": group_id, "mediatype": "image", "mimetype": "image/jpeg",
                      "caption": texto, "media": img_url},
                headers=headers, timeout=30
            )
            if r.status_code in (200, 201):
                return
        requests.post(
            f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            json={"number": group_id, "text": texto},
            headers=headers, timeout=30
        )
    except Exception as e:
        log.warning(f"WhatsApp custom erro: {e}")


def ciclo_teste():
    """Busca 1 produto da Shopee e posta no grupo de teste."""
    log.info("🧪 Ciclo de teste iniciado...")
    try:
        from shopee_api import buscar_todos_produtos as buscar_shopee_teste
        produtos = buscar_shopee_teste()
        if not produtos:
            log.warning("🧪 Ciclo teste: nenhum produto Shopee encontrado")
            return
        produto = produtos[0]
        log.info(f"🧪 Testando: {produto.get('nome', '')[:50]}")
        imagem_path = gerar_imagem(produto)
        postar_whatsapp_teste(produto, imagem_path)
    except Exception as e:
        log.error(f"🧪 Ciclo teste erro: {e}")


def iniciar_api_historico():
    """Sobe mini servidor HTTP para expor historico do banco."""
    import json as _json
    from http.server import HTTPServer, BaseHTTPRequestHandler

    WEB_API_KEY = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # silencia logs do servidor

        def do_POST(self):
            if self.path.startswith("/ciclo") and not self.path.startswith("/ciclo_tb"):
                api_key = self.headers.get("X-API-Key", "")
                if api_key != WEB_API_KEY:
                    self.send_response(401)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = _json.loads(self.rfile.read(length)) if length else {}
                    qtde        = int(body.get("qtde", POSTS_POR_CICLO))
                    usar_tg     = body.get("telegram", True)
                    usar_wa_pri = body.get("wa_principal", True)
                    usar_wa_tst = body.get("wa_teste", False)
                    usar_ml     = body.get("usar_ml", True)
                    usar_shopee = body.get("usar_shopee", True)
                    usar_ali    = body.get("usar_ali", True)
                    usar_amazon = body.get("usar_amazon", True)

                    import threading as _th
                    def _rodar():
                        try:
                            import time as _t
                            log.info(f"🎮 Ciclo manual via Web — {qtde} post(s)")
                            produtos = montar_pipeline(usar_ml=usar_ml, usar_shopee=usar_shopee, usar_ali=usar_ali, usar_amazon=usar_amazon)
                            log.info(f"🎮 Pipeline retornou {len(produtos)} produto(s)")
                            # Filtra lojas se necessário (garantia dupla)
                            if not usar_ml:
                                produtos = [p for p in produtos if p.get("loja") != "MERCADOLIVRE"]
                            if not usar_shopee:
                                produtos = [p for p in produtos if p.get("loja") != "SHOPEE"]
                            if not usar_ali:
                                produtos = [p for p in produtos if p.get("loja") != "ALIEXPRESS"]
                            if not usar_amazon:
                                produtos = [p for p in produtos if p.get("loja") != "AMAZON"]
                            log.info(f"🎮 Após filtro lojas: {len(produtos)} produto(s)")
                            if not produtos:
                                log.warning("🎮 Nenhum produto disponível para ciclo manual")
                                return
                            postou = 0
                            for produto in produtos:
                                if postou >= qtde:
                                    break
                                # Verificar histórico em tempo real (evita repetição em disparos rápidos)
                                hash_p = hashlib.md5(produto["nome"].encode()).hexdigest()
                                if ja_postado(hash_p):
                                    log.info(f"🎮 Pulado (já postado recentemente): {produto['nome'][:40]}")
                                    continue
                                log.info(f"🎮 Postando: {produto['nome'][:50]}")
                                try:
                                    imagem = gerar_imagem(produto)
                                    publicou = False
                                    if usar_tg:
                                        produto_tg = {**produto, "imagem_url": ""}
                                        ok_tg = postar_telegram(produto_tg, imagem)
                                        if ok_tg:
                                            publicou = True
                                            log.info("🎮 ✅ Telegram OK")
                                    if usar_wa_pri:
                                        postar_whatsapp_custom(produto, imagem, WHATSAPP_GROUP_ID)
                                        publicou = True
                                        log.info("🎮 ✅ WhatsApp Principal OK")
                                    if usar_wa_tst:
                                        postar_whatsapp_custom(produto, imagem, WHATSAPP_TEST_GROUP_ID)
                                        publicou = True
                                        log.info("🎮 ✅ WhatsApp Teste OK")
                                    if publicou:
                                        registrar_post(produto, "WEB_MANUAL")
                                        postou += 1
                                    _t.sleep(8)
                                except Exception as ep:
                                    log.error(f"🎮 Erro ao postar produto: {ep}")
                                    continue
                            log.info(f"🎮 Ciclo manual concluído — {postou} post(s)")
                        except Exception as e:
                            log.error(f"🎮 Ciclo manual erro: {e}")
                    _th.Thread(target=_rodar, daemon=True).start()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write((_json.dumps({"ok": True, "msg": f"Ciclo iniciado — {qtde} post(s) agendados!"})).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_json.dumps({"ok": False, "erro": str(e)}).encode())

            elif self.path.startswith("/ciclo_tb"):
                api_key = self.headers.get("X-API-Key", "")
                if api_key != WEB_API_KEY:
                    self.send_response(401)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = _json.loads(self.rfile.read(length)) if length else {}
                    usar_tg     = body.get("telegram", True)
                    usar_wa_pri = body.get("wa_principal", True)
                    usar_wa_tst = body.get("wa_teste", False)
                    qtde        = int(body.get("qtde", POSTS_POR_CICLO))
                    import threading as _th
                    def _rodar_tb():
                        try:
                            import time as _t
                            log.info(f"🤑 Ciclo Ticket Baixo manual — {qtde} post(s) | TG={usar_tg} PRI={usar_wa_pri} TST={usar_wa_tst}")
                            produtos = montar_pipeline_ticket_baixo()
                            if not produtos:
                                log.warning("🤑 Nenhum produto ticket baixo disponível")
                                return
                            log.info(f"🤑 {len(produtos)} produto(s) disponíveis")
                            postou = 0
                            for produto in produtos[:qtde]:
                                log.info(f"🤑 Postando: {produto['nome'][:50]}")
                                try:
                                    imagem = gerar_imagem(produto)
                                    publicou = False
                                    if usar_tg:
                                        produto_tg = {**produto, "imagem_url": ""}
                                        if postar_telegram(produto_tg, imagem):
                                            publicou = True
                                            log.info("🤑 ✅ Telegram OK")
                                    if usar_wa_pri:
                                        postar_whatsapp_custom(produto, imagem, WHATSAPP_GROUP_ID)
                                        publicou = True
                                        log.info("🤑 ✅ WA Principal OK")
                                    if usar_wa_tst:
                                        postar_whatsapp_custom(produto, imagem, WHATSAPP_TEST_GROUP_ID)
                                        publicou = True
                                        log.info("🤑 ✅ WA Teste OK")
                                    if publicou:
                                        registrar_post(produto, "WEB_MANUAL")
                                        postou += 1
                                    _t.sleep(8)
                                except Exception as ep:
                                    log.error(f"🤑 Erro produto: {ep}")
                                    continue
                            log.info(f"🤑 Ciclo Ticket Baixo concluído — {postou} post(s)")
                        except Exception as e:
                            log.error(f"🤑 Ciclo TB erro: {e}")
                    _th.Thread(target=_rodar_tb, daemon=True).start()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write((_json.dumps({"ok": True, "msg": f"Ciclo Ticket Baixo iniciado — {qtde} post(s)!"})).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_json.dumps({"ok": False, "erro": str(e)}).encode())

            elif self.path.startswith("/limpar_historico"):
                api_key = self.headers.get("X-API-Key", "")
                if api_key != WEB_API_KEY:
                    self.send_response(401)
                    self.end_headers()
                    return
                try:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("DELETE FROM postados")
                    total = c.rowcount
                    conn.commit()
                    conn.close()
                    log.info(f"🗑️ Histórico limpo via painel — {total} registro(s) removido(s)")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_json.dumps({"ok": True, "msg": f"{total} registro(s) removido(s)"}).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_json.dumps({"ok": False, "erro": str(e)}).encode())

            elif self.path.startswith("/registrar"):
                api_key = self.headers.get("X-API-Key", "")
                if api_key != WEB_API_KEY:
                    self.send_response(401)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = _json.loads(self.rfile.read(length))
                    produto = {
                        "nome": body.get("nome", ""),
                        "preco": body.get("preco", 0),
                        "loja": body.get("loja", ""),
                        "link_afiliado": body.get("link", ""),
                    }
                    origem = body.get("origem", "WEB")
                    registrar_post(produto, origem)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok": true}')
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def do_GET(self):
            if self.path.startswith("/historico"):
                # Verifica API key
                api_key = self.headers.get("X-API-Key", "")
                if api_key != WEB_API_KEY:
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"erro": "Nao autorizado"}')
                    return
                try:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("""
                        SELECT id, nome, preco, loja, postado_em, COALESCE(origem, 'BOT'), COALESCE(link, '')
                        FROM postados
                        ORDER BY postado_em DESC
                        LIMIT 100
                    """)
                    rows = c.fetchall()
                    conn.close()
                    data = [{"id": r[0], "nome": r[1], "preco": r[2], "loja": r[3], "postado_em": r[4], "origem": r[5], "link": r[6]} for r in rows]
                    body = _json.dumps(data).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(_json.dumps({"erro": str(e)}).encode())
            else:
                self.send_response(404)
                self.end_headers()

    port = int(os.getenv("BOT_API_PORT", "8081"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    log.info(f"📊 API histórico rodando na porta {port}")
    server.serve_forever()


def main():
    init_db()
    log.info("🤖 OlhaissoTech Bot v6.0 iniciado!")
    log.info(f"📢 Canal: {TELEGRAM_CHANNEL}")
    log.info(f"⏰ Horários: {', '.join(HORARIOS)}")
    log.info(f"📦 Posts por ciclo: {POSTS_POR_CICLO}")
    log.info(f"🎯 Máx por tema: {MAX_POR_TEMA}")
    log.info(f"🗓️ Sem repetir por: {HORAS_SEM_REPETIR} horas\n")
    for h in HORARIOS:
        schedule.every().day.at(h).do(ciclo)
    for h in HORARIO_COPA:
        schedule.every().day.at(h).do(ciclo)
    log.info(f"📺🇧🇷 Ciclo Copa 2026 (TVs): {chr(44).join(HORARIO_COPA)}")
    log.info(f"💰 Ciclo ticket baixo (≤R${PRECO_TICKET_BAIXO:.0f}): {', '.join(HORARIO_TICKET_BAIXO)}")
    log.info(f"🏠 Ciclo eletrodomésticos (ML+Amazon): {', '.join(HORARIOS_ELETRO)}")
    # Sobe API de histórico em thread separada
    import threading
    t = threading.Thread(target=iniciar_api_historico, daemon=True)
    t.start()
    # Dispara 1 oferta de teste no grupo teste a cada deploy (em thread para não bloquear o boot)
    t_teste = threading.Thread(target=ciclo_teste, daemon=True)
    t_teste.start()
    log.info("⏳ Aguardando próximo horário agendado...")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
