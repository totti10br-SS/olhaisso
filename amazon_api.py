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
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "")

CATEGORIAS = [
    ("Smartphones",      "https://www.amazon.com.br/gp/bestsellers/wireless"),
    ("TVs",              "https://www.amazon.com.br/gp/bestsellers/electronics/?ie=UTF8&pg=1#1"),
    ("Informática",      "https://www.amazon.com.br/gp/bestsellers/computers"),
    ("Games",            "https://www.amazon.com.br/gp/bestsellers/videogames"),
    ("Eletrodomésticos", "https://www.amazon.com.br/gp/bestsellers/kitchen"),
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
    if SCRAPERAPI_KEY:
        try:
            scraper_url = f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={url}&country_code=br"
            r = requests.get(scraper_url, timeout=12)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            log.warning(f"ScraperAPI Amazon falhou: {e}")
    return None


def _is_bloqueado(nome):
    return any(p in nome.lower() for p in PALAVRAS_BLOQUEADAS)


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
            for item in parser.items[:10]:
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
                produtos.append({
                    "nome":           nome,
                    "preco":          preco,
                    "preco_original": round(preco * 1.3, 2),
                    "desconto":       23,
                    "loja":           "AMAZON",
                    "frete":          "✅ Frete grátis Prime",
                    "link_afiliado":  f"https://www.amazon.com.br/dp/{asin}?tag={AMAZON_TAG}",
                    "imagem_url":     f"https://images-na.ssl-images-amazon.com/images/P/{asin}.jpg",
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
