import os
import re
import time
import hashlib
import logging
import requests
from html.parser import HTMLParser

log = logging.getLogger(__name__)

AMAZON_TAG     = os.getenv("AMAZON_TAG", "olhaissotech-20")
PRECO_MAXIMO   = float(os.getenv("PRECO_MAXIMO", 3000))
SCRAPINGANT_KEY = os.getenv("SCRAPINGANT_KEY", "")
ZENROWS_KEY     = os.getenv("ZENROWS_KEY", "")      # fallback
SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY", "")   # fallback

CATEGORIAS = [
    # Mais Vendidos
    ("Smartphones",           "https://www.amazon.com.br/gp/bestsellers/electronics/16243890011"),
    ("TVs",                   "https://www.amazon.com.br/gp/bestsellers/electronics/16243822011"),
    ("Monitores",             "https://www.amazon.com.br/gp/bestsellers/computers/16364845011"),
    ("Gabinetes",             "https://www.amazon.com.br/gp/bestsellers/computers/16364807011"),
    ("Placas de Vídeo p1",    "https://www.amazon.com.br/gp/bestsellers/computers/16364811011/ref=zg_bs_pg_1_computers?ie=UTF8&pg=1"),
    ("Placas de Vídeo p2",    "https://www.amazon.com.br/gp/bestsellers/computers/16364811011/ref=zg_bs_pg_2_computers?ie=UTF8&pg=2"),
    ("Informática p1",        "https://www.amazon.com.br/gp/bestsellers/computers/ref=zg_bs_pg_1_computers?ie=UTF8&pg=1"),
    ("Informática p2",        "https://www.amazon.com.br/gp/bestsellers/computers/ref=zg_bs_pg_2_computers?ie=UTF8&pg=2"),
    ("Games",                 "https://www.amazon.com.br/gp/bestsellers/videogames"),
    ("Eletrodomésticos",      "https://www.amazon.com.br/gp/bestsellers/kitchen"),
    ("Áudio e Fones",         "https://www.amazon.com.br/gp/bestsellers/electronics/16244120011"),
    # Produtos em Alta
    ("Em Alta Informática p1","https://www.amazon.com.br/gp/movers-and-shakers/computers/ref=zg_bsms_pg_1_computers?ie=UTF8&pg=1"),
    ("Em Alta Informática p2","https://www.amazon.com.br/gp/movers-and-shakers/computers/ref=zg_bsms_pg_2_computers?ie=UTF8&pg=2"),
    ("Em Alta Eletrônicos p1","https://www.amazon.com.br/gp/movers-and-shakers/electronics/ref=zg_bsms_pg_1_electronics?ie=UTF8&pg=1"),
    ("Em Alta Eletrônicos p2","https://www.amazon.com.br/gp/movers-and-shakers/electronics/ref=zg_bsms_pg_2_electronics?ie=UTF8&pg=2"),
]

PALAVRAS_BLOQUEADAS = [
    "perfume", "shampoo", "sabonete", "creme", "maquiagem", "roupa",
    "camisa", "tenis", "sapato", "sandalia", "calcado", "vestuario",
    "suplemento", "vitamina", "remedio", "brinquedo", "livro", "album",
    "figurinha", "sofa", "colchao", "cortina", "tapete", "telescopio",
    "microscopio", "luneta",
    # Periféricos não desejados
    "cartucho", "tinta hp", "tinta epson", "tinta canon", "refil",
    "pilha", "pilhas", "bateria aa", "bateria aaa",
    # Bolsas e acessórios não tech
    "mochila", "bolsa", "mala", "carteira",
    # Nomes inválidos
    "sem sistema operacional",
]


class AmazonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self._in_title = False
        self._in_price = False
        self._current = {}

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        if tag == "a":
            href = attrs_dict.get("href", "")
            m = re.search(r"/dp/([A-Z0-9]{10})", href)
            if m and "asin" not in self._current:
                self._current["asin"] = m.group(1)
        if "p13n-sc-truncate" in cls or "_cDEzb_p13n-sc-css-line-clamp" in cls:
            self._in_title = True
        if "p13n-sc-price" in cls or "_cDEzb_p13n-sc-price" in cls:
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


def _fetch_url(url):
    # Tenta direto primeiro (Amazon às vezes permite)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and "bestsellers" in r.text:
            return r.text
    except Exception as e:
        log.warning(f"Amazon direto falhou: {e}")

    # ScrapingAnt
    if SCRAPINGANT_KEY:
        try:
            # browser=true necessário para páginas Amazon com JS — tenta false primeiro (mais barato)
            for browser_mode in ["false", "true"]:
                params = {
                    "url":           url,
                    "x-api-key":     SCRAPINGANT_KEY,
                    "proxy_country": "BR",
                    "browser":       browser_mode,
                }
                r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=45)
                log.info(f"Amazon ScrapingAnt browser={browser_mode} {r.status_code} → {url[-40:]}")
                if r.status_code == 200 and len(r.text) > 1000:
                    return r.text
                if r.status_code != 200:
                    log.warning(f"Amazon ScrapingAnt erro: {r.text[:100]}")
                    break  # se der erro de auth/quota, não tenta de novo
        except Exception as e:
            log.warning(f"Amazon ScrapingAnt falhou: {e}")

    # Fallback ZenRows
    if ZENROWS_KEY:
        try:
            params = {
                "url":           url,
                "apikey":        ZENROWS_KEY,
                "js_render":     "false",
                "antibot":       "true",
                "premium_proxy": "true",
                "proxy_country": "br",
            }
            r = requests.get("https://api.zenrows.com/v1/", params=params, timeout=30)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            log.warning(f"Amazon ZenRows falhou: {e}")

    return None


def _is_bloqueado(nome):
    return any(p in nome.lower() for p in PALAVRAS_BLOQUEADAS)


def buscar_imagem_amazon(produto):
    """Busca imagem real do produto Amazon — chamar só na hora de postar."""
    asin = produto.get("asin", "")
    if not asin:
        # Tenta extrair do link
        m = re.search(r"/dp/([A-Z0-9]{10})", produto.get("link_afiliado", ""))
        if m:
            asin = m.group(1)
    if not asin:
        return ""
    return _buscar_imagem_produto(asin)


def _buscar_imagem_produto(asin):
    """Busca imagem real do produto via ZenRows na página do produto."""
    if not SCRAPINGANT_KEY and not ZENROWS_KEY:
        return ""
    try:
        url = f"https://www.amazon.com.br/dp/{asin}"

        if SCRAPINGANT_KEY:
            params = {
                "url":           url,
                "x-api-key":     SCRAPINGANT_KEY,
                "proxy_country": "BR",
                "browser":       "false",
            }
            r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=20)
        elif ZENROWS_KEY:
            params = {
                "url":           url,
                "apikey":        ZENROWS_KEY,
                "js_render":     "false",
                "antibot":       "true",
                "premium_proxy": "true",
                "proxy_country": "br",
            }
            r = requests.get("https://api.zenrows.com/v1/", params=params, timeout=20)
        else:
            return ""

        if r.status_code != 200:
            return ""

        for pattern in [
            r'"hiRes":"(https://[^"]+\.jpg)"',
            r'"large":"(https://[^"]+\.jpg)"',
            r'data-old-hires="(https://[^"]+\.jpg)"',
            r'"mainUrl":"(https://[^"]+\.jpg)"',
        ]:
            m = re.search(pattern, r.text)
            if m:
                log.info(f"Amazon imagem via ScrapingAnt: {m.group(1)[:60]}")
                return m.group(1)
    except Exception as e:
        log.warning(f"Amazon imagem erro: {e}")
    return ""


def buscar_todos_produtos():
    produtos = []
    for nome_cat, url in CATEGORIAS:
        log.info(f"Amazon [{nome_cat}]: buscando...")
        try:
            html = _fetch_url(url)
            if not html:
                log.warning(f"Amazon [{nome_cat}]: sem resposta")
                continue
            parser = AmazonParser()
            parser.feed(html)
            for item in parser.items[:20]:
                try:
                    preco = float(
                        item["preco_txt"]
                        .replace("R$", "").replace(".", "").replace(",", ".").strip()
                    )
                except Exception:
                    continue
                if preco <= 0 or preco > PRECO_MAXIMO:
                    continue
                nome = item["nome"]
                if _is_bloqueado(nome):
                    log.info(f"Amazon bloqueado: {nome[:40]}")
                    continue
                # Tenta ASIN real; fallback regex no HTML; fallback hash (nunca pula)
                asin = item.get("asin", "")
                if not asin and html:
                    idx = html.find(nome[:25])
                    if idx > 0:
                        m = re.search(r"/dp/([A-Z0-9]{10})", html[max(0,idx-500):idx+500])
                        if m:
                            asin = m.group(1)
                if not asin:
                    asin = hashlib.md5(nome.encode()).hexdigest()[:10].upper()
                    log.warning(f"Amazon: ASIN hash para '{nome[:40]}'")
                else:
                    log.info(f"Amazon: ASIN real {asin} → {nome[:40]}")

                # Imagem NÃO buscada aqui — será buscada só para produtos selecionados para postar
                produtos.append({
                    "nome":           nome,
                    "preco":          preco,
                    "preco_original": round(preco * 1.3, 2),
                    "desconto":       23,
                    "loja":           "AMAZON",
                    "frete":          "✅ Frete grátis Prime",
                    "link_afiliado":  f"https://www.amazon.com.br/dp/{asin}?tag={AMAZON_TAG}",
                    "imagem_url":     "",  # preenchida depois pelo bot ao postar
                    "asin":           asin,
                    "score":          1,
                    "fontes":         ["amazon"],
                    "categoria":      nome_cat,
                })
            log.info(f"Amazon [{nome_cat}]: {len(parser.items)} brutos → {len(produtos)} acumulados")
            time.sleep(2)
        except Exception as e:
            log.error(f"Amazon [{nome_cat}] erro: {e}")
            continue
    log.info(f"Amazon: {len(produtos)} produto(s) válidos no total")
    return produtos
