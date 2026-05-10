"""
OlhaissoTech — Painel de Publicação Manual
Fluxo 1: Link de afiliado pronto → preenche dados → publica Telegram + WhatsApp
Fluxo 2: Link Shopee/AliExpress → extrai nome → publica Telegram + WhatsApp
"""

import os
import re
import json
import hashlib
import time
import requests
from urllib.parse import urlparse, unquote
from flask import Flask, request, jsonify, session, redirect, render_template_string

from bot import (
    gerar_imagem,
    postar_telegram,
    postar_whatsapp,
    AMAZON_TAG,
    EVOLUTION_URL,
    EVOLUTION_APIKEY,
    EVOLUTION_INSTANCE,
    WHATSAPP_GROUP_ID,
    WHATSAPP_TEST_GROUP_ID,
)
import requests as _req

def fazer_upload_imgbb(imagem_path):
    """Faz upload da imagem gerada para imgbb e retorna URL publica HD."""
    IMGBB_KEY = os.getenv("IMGBB_KEY", "")
    if not IMGBB_KEY or not imagem_path:
        return None
    try:
        import base64
        with open(imagem_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        r = _req.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_KEY, "image": img_b64},
            timeout=20
        )
        if r.status_code == 200:
            return r.json()["data"]["url"]
    except Exception as e:
        print("imgbb upload erro: " + str(e))
    return None


def postar_whatsapp_grupo(produto, imagem_path, group_id):
    """Posta no grupo WhatsApp especificado usando imagem gerada pelo bot (HD)."""
    if not EVOLUTION_URL or not group_id:
        return
    try:
        nome    = produto.get("nome", "")
        preco   = produto.get("preco", 0)
        orig    = produto.get("preco_original", 0)
        desc    = produto.get("desconto", 0)
        link    = produto.get("link_afiliado", "")
        loja    = produto.get("loja", "")
        loja_label = {
            "ALIEXPRESS": "AliExpress", "SHOPEE": "Shopee",
            "AMAZON": "Amazon", "MERCADOLIVRE": "Mercado Livre"
        }.get(loja, loja)
        badge = "VIRAL AGORA" if produto.get("score", 0) >= 3 else "TENDENCIA" if produto.get("score", 0) == 2 else "OFERTA DO DIA"
        def fmt(v):
            return "R$ {:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")
        linhas = [
            "*OlhaissoTech* -- " + badge,
            "--------------------",
            "",
            "*" + nome + "*",
            "",
        ]
        if desc > 0:
            eco = round(orig - preco, 2)
            linhas.append(str(desc) + "% OFF  |  Economia de " + fmt(eco))
        if orig > preco:
            linhas.append("")
            linhas.append("De " + fmt(orig) + " por apenas")
        linhas.append(fmt(preco))
        linhas.append("")
        linhas.append(loja_label)
        linhas.append("")
        linhas.append("COMPRAR AGORA:")
        linhas.append(link)
        linhas.append("")
        linhas.append("--------------------")
        linhas.append("OlhaissoTech | Gadgets com o melhor preco")
        texto = "\n".join(linhas)
        headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}

        # Usa imagem HD do produto diretamente (foto limpa, sem card gerado)
        img_url = produto.get('imagem_url', '')

        if img_url:
            payload = {
                "number": group_id, "mediatype": "image",
                "mimetype": "image/jpeg", "caption": texto, "media": img_url,
            }
            r = _req.post(
                EVOLUTION_URL + "/message/sendMedia/" + EVOLUTION_INSTANCE,
                json=payload, headers=headers, timeout=30
            )
            if r.status_code in (200, 201):
                return

        payload_txt = {"number": group_id, "text": texto}
        _req.post(
            EVOLUTION_URL + "/message/sendText/" + EVOLUTION_INSTANCE,
            json=payload_txt, headers=headers, timeout=30
        )
    except Exception as e:
        print("WhatsApp grupo erro: " + str(e))


app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "olhaissoadmin")

# Credenciais Shopee e AliExpress
SHOPEE_APP_ID = "18307831002"
SHOPEE_SECRET = "5TCZ4KND77VOJV5QNUX7PMYKTVPF23XT"
SHOPEE_URL    = "https://open-api.affiliate.shopee.com.br/graphql"
ALIEXPRESS_APP_KEY    = "530504"
ALIEXPRESS_APP_SECRET = "ubsjVAWmokbBynXv0uYsQz2PJSwsshXP"
ALIEXPRESS_TRACKING   = "default"


def encurtar_link(url_longa):
    try:
        r = requests.get(f"https://tinyurl.com/api-create.php?url={url_longa}", timeout=5)
        if r.status_code == 200 and r.text.startswith("https://"):
            return r.text.strip()
    except:
        pass
    return url_longa


def gerar_link_afiliado_shopee(url_produto):
    """Converte link de produto Shopee em link de afiliado via API GraphQL."""
    try:
        query = """mutation generateShortLink($input: GenerateShortLinkInput!) {
  generateShortLink(input: $input) {
    shortLink
  }
}"""
        body = {
            "query": query,
            "operationName": "generateShortLink",
            "variables": {"input": {"originUrl": url_produto}}
        }
        payload_str = json.dumps(body, separators=(",", ":"))
        timestamp = int(time.time())
        fator = SHOPEE_APP_ID + str(timestamp) + payload_str + SHOPEE_SECRET
        sign = hashlib.sha256(fator.encode("utf-8")).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={SHOPEE_APP_ID},Timestamp={timestamp},Signature={sign}",
        }
        r = requests.post(SHOPEE_URL, data=payload_str, headers=headers, timeout=15)
        data = r.json()
        link = data.get("data", {}).get("generateShortLink", {}).get("shortLink", "")
        if link:
            return link
    except Exception as e:
        print(f"Shopee gerar link erro: {e}")
    return encurtar_link(url_produto)


def gerar_link_afiliado_aliexpress(url_produto):
    """Converte link de produto AliExpress em link de afiliado via API."""
    try:
        timestamp = str(int(time.time() * 1000))
        params = {
            "app_key":     ALIEXPRESS_APP_KEY,
            "timestamp":   timestamp,
            "sign_method": "md5",
            "method":      "aliexpress.affiliate.link.generate",
            "promotion_link_type": "0",
            "source_values": url_produto,
            "tracking_id": ALIEXPRESS_TRACKING,
        }
        keys = sorted(params.keys())
        base = ALIEXPRESS_APP_SECRET + "".join(f"{k}{params[k]}" for k in keys) + ALIEXPRESS_APP_SECRET
        params["sign"] = hashlib.md5(base.encode("utf-8")).hexdigest().upper()

        r = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15)
        data = r.json()
        resp = data.get("aliexpress_affiliate_link_generate_response", {}).get("resp_result", {})
        if resp.get("resp_code") == 200:
            links = resp.get("result", {}).get("promotion_links", {}).get("promotion_link", [])
            if links:
                return links[0].get("promotion_link", url_produto)
    except Exception as e:
        print(f"AliExpress gerar link erro: {e}")
    return encurtar_link(url_produto)


def busca_shopee_sem_filtro(keyword, limit=10):
    """Busca Shopee sem filtros — para busca induzida do painel."""
    try:
        query = """query getProducts($keyword: String!, $limit: Int!, $page: Int!) {
  productOfferV2(listType: 0, sortType: 2, keyword: $keyword, limit: $limit, page: $page) {
    nodes {
      productName priceMin priceDiscountRate imageUrl offerLink productLink
    }
  }
}"""
        body = {"query": query, "operationName": "getProducts",
                "variables": {"keyword": keyword, "limit": limit, "page": 1}}
        payload_str = json.dumps(body, separators=(",", ":"))
        timestamp = int(time.time())
        fator = SHOPEE_APP_ID + str(timestamp) + payload_str + SHOPEE_SECRET
        sign = hashlib.sha256(fator.encode("utf-8")).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={SHOPEE_APP_ID},Timestamp={timestamp},Signature={sign}",
        }
        r = requests.post(SHOPEE_URL, data=payload_str, headers=headers, timeout=15)
        data = r.json()
        nodes = data.get("data", {}).get("productOfferV2", {}).get("nodes", []) or []
        produtos = []
        for item in nodes:
            try:
                preco = float(str(item.get("priceMin", "0")).replace(",", "."))
                desc_raw = item.get("priceDiscountRate", "0") or "0"
                desconto = int(str(desc_raw).replace("%", "").strip() or 0)
            except:
                continue
            nome = item.get("productName", "")
            link_original = item.get("offerLink") or item.get("productLink", "")
            imagem = item.get("imageUrl", "")
            if not nome or not link_original:
                continue
            preco_orig = round(preco / (1 - desconto / 100), 2) if desconto > 0 else round(preco * 1.3, 2)
            produtos.append({
                "nome": nome, "preco": round(preco, 2), "preco_original": preco_orig,
                "desconto": desconto, "loja": "SHOPEE", "frete": "✅ Frete grátis",
                "link_afiliado": encurtar_link(link_original), "imagem_url": imagem,
                "score": 1, "fontes": [],
            })
        return produtos
    except Exception as e:
        print(f"busca_shopee_sem_filtro erro: {e}")
        return []


def busca_ml_por_keyword(keyword, limit=20):
    """Busca ML por keyword — mesmo processo do mercadolivre_api.py via ScrapingAnt."""
    import json as _json, hashlib as _hashlib
    SCRAPINGANT_KEY = os.getenv("SCRAPINGANT_KEY", "")
    SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY", "")
    if not SCRAPINGANT_KEY and not SCRAPERAPI_KEY:
        print("busca_ml_por_keyword: nenhuma chave de scraping configurada")
        return []
    try:
        from mercadolivre_link import gerar_link_afiliado_ml

        # Scraper fetch usando ScrapingAnt com fallback ScraperAPI
        def _scraper_fetch(url):
            try:
                if SCRAPINGANT_KEY:
                    params = {
                        "url":           url,
                        "x-api-key":     SCRAPINGANT_KEY,
                        "proxy_country": "BR",
                        "browser":       "false",
                    }
                    r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=60)
                    print("ML busca ScrapingAnt " + str(r.status_code) + " -> " + url[:60])
                else:
                    payload = {
                        "api_key":      SCRAPERAPI_KEY,
                        "url":          url,
                        "country_code": "br",
                        "render":       "false",
                    }
                    r = requests.get("https://api.scraperapi.com", params=payload, timeout=60)
                    print("ML busca ScraperAPI " + str(r.status_code) + " -> " + url[:60])
                if r.status_code == 200:
                    return r.text
                return None
            except Exception as e:
                print("ML busca scraper erro: " + str(e))
                return None

        # Mesma função extrair_produtos_html do mercadolivre_api.py
        def _extrair(html):
            if not html:
                return []
            try:
                idx = html.find('"results":[{')
                if idx == -1:
                    idx = html.find('"items":[{')
                if idx == -1:
                    return []
                start = html.rfind('[', 0, idx + 15)
                depth, end = 0, start
                for i, c in enumerate(html[start:], start):
                    if c == '[': depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                    if i - start > 500000:
                        break
                data = _json.loads(html[start:end])
                if isinstance(data, list) and len(data) > 0:
                    return data
            except Exception as e:
                print("ML busca parse erro: " + str(e))
            return []

        # Mesma função processar_item do mercadolivre_api.py
        def _processar(item, kw_lower):
            try:
                if not isinstance(item, dict):
                    return None
                card = item.get("card", {})
                if not card:
                    return None
                metadata   = card.get("metadata", {}) or {}
                components = card.get("components", []) or []
                pictures   = card.get("pictures", []) or []
                item_id    = metadata.get("id", "")
                url_prod   = metadata.get("url", "")
                if url_prod and not url_prod.startswith("http"):
                    url_prod = "https://" + url_prod
                if not url_prod:
                    return None
                nome = ""
                preco = 0.0
                preco_orig = 0.0
                imagem = ""
                frete_ok = False
                for comp in components:
                    if not isinstance(comp, dict):
                        continue
                    ctype = comp.get("type", "").lower()
                    cdata = comp.get(ctype, {})
                    if not isinstance(cdata, dict):
                        cdata = {}
                    if ctype == "title":
                        nome = cdata.get("text", "") or nome
                    elif ctype == "price":
                        curr = cdata.get("current_price", {}) or {}
                        prev = cdata.get("previous_price", {}) or {}
                        preco = float(curr.get("value", 0) or 0)
                        preco_orig = float(prev.get("value", 0) or 0)
                    elif ctype == "shipping":
                        if "grátis" in cdata.get("text", "").lower():
                            frete_ok = True
                if not nome:
                    nome = metadata.get("title", "")
                nome = nome.strip()
                if not nome:
                    return None
                if preco <= 0:
                    return None
                # Filtra por keyword — qualquer palavra da busca deve estar no nome
                if kw_lower:
                    palavras = [w for w in kw_lower.split() if len(w) > 2]
                    if palavras and not any(w in nome.lower() for w in palavras):
                        return None
                desconto = int((1 - preco / preco_orig) * 100) if preco_orig > preco else 0
                # Imagem igual ao mercadolivre_api.py
                if not imagem and isinstance(pictures, dict):
                    try:
                        pics_list = pictures.get("pictures", [])
                        if pics_list and isinstance(pics_list[0], dict):
                            pic_id = pics_list[0].get("id", "")
                            if pic_id:
                                imagem = "https://http2.mlstatic.com/D_NQ_NP_" + pic_id + "-F.jpg"
                    except Exception:
                        pass
                frete_txt = "✅ Frete grátis" if frete_ok else "🚚 Frete a calcular"
                link_curto = gerar_link_afiliado_ml(url_prod, item_id) or url_prod
                return {
                    "nome": nome, "preco": round(preco, 2),
                    "preco_original": round(preco_orig, 2) if preco_orig > preco else 0,
                    "desconto": desconto, "loja": "MERCADOLIVRE",
                    "frete": frete_txt, "link_afiliado": link_curto,
                    "imagem_url": imagem, "score": 1, "fontes": [],
                }
            except Exception as e:
                print("ML processar erro: " + str(e))
                return None

        # URL de busca por keyword — mesmo formato das categorias
        kw_encoded = keyword.replace(" ", "+")
        url = "https://lista.mercadolivre.com.br/" + kw_encoded
        html = _scraper_fetch(url)
        items = _extrair(html)
        print("ML busca: " + str(len(items)) + " itens brutos para '" + keyword + "'")

        kw_lower = keyword.lower()
        todos = []
        vistos = set()
        for item in items:
            p = _processar(item, kw_lower)
            if p:
                chave = _hashlib.md5(p["nome"].encode()).hexdigest()
                if chave not in vistos:
                    vistos.add(chave)
                    todos.append(p)
            if len(todos) >= limit:
                break

        print("ML busca: " + str(len(todos)) + " produtos validos para '" + keyword + "'")
        return todos
    except Exception as e:
        print("busca_ml_por_keyword erro: " + str(e))
        return []

def busca_aliexpress_sem_filtro(keyword, limit=10):
    """Busca AliExpress sem filtros — para busca induzida do painel."""
    try:
        timestamp = str(int(time.time() * 1000))
        params = {
            "app_key": ALIEXPRESS_APP_KEY, "timestamp": timestamp,
            "sign_method": "md5", "method": "aliexpress.affiliate.product.query",
            "keywords": keyword, "page_no": "1", "page_size": str(limit),
            "sort": "LAST_VOLUME_DESC", "target_currency": "BRL",
            "target_language": "PT", "tracking_id": ALIEXPRESS_TRACKING,
            "ship_to_country": "BR",
            "fields": "product_id,product_title,target_sale_price,target_original_price,discount,product_main_image_url,promotion_link",
        }
        keys = sorted(params.keys())
        base = ALIEXPRESS_APP_SECRET + "".join(f"{k}{params[k]}" for k in keys) + ALIEXPRESS_APP_SECRET
        params["sign"] = hashlib.md5(base.encode("utf-8")).hexdigest().upper()
        r = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15)
        data = r.json()
        resp = data.get("aliexpress_affiliate_product_query_response", {}).get("resp_result", {})
        if resp.get("resp_code") != 200:
            return []
        items = resp.get("result", {}).get("products", {}).get("product", [])
        produtos = []
        for item in items:
            try:
                preco = float(str(item.get("target_sale_price", "0")).replace(",", "."))
                preco_orig = float(str(item.get("target_original_price", "0")).replace(",", "."))
            except:
                continue
            desconto = int((1 - preco / preco_orig) * 100) if preco_orig > preco else 0
            nome = item.get("product_title", "")
            link = item.get("promotion_link", "")
            imagem = item.get("product_main_image_url", "")
            if not nome or not link:
                continue
            produtos.append({
                "nome": nome, "preco": round(preco, 2), "preco_original": round(preco_orig, 2),
                "desconto": desconto, "loja": "ALIEXPRESS", "frete": "🚢 Frete grátis",
                "link_afiliado": encurtar_link(link), "imagem_url": imagem,
                "score": 1, "fontes": [],
            })
        return produtos
    except Exception as e:
        print(f"busca_aliexpress_sem_filtro erro: {e}")
        return []

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>👀 OlhaissoTech — Painel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #111; color: #fff; font-family: -apple-system, sans-serif; min-height: 100vh; }
  .header { background: #FF6B1A; padding: 16px 20px; display: flex; align-items: center; gap: 10px; }
  .header h1 { font-size: 20px; font-weight: 800; }
  .container { max-width: 600px; margin: 0 auto; padding: 20px; }
  .container.wide { max-width: 1100px; }
  .tabs { display: flex; gap: 8px; margin-bottom: 16px; }
  .tab { flex: 1; padding: 12px; border-radius: 10px; border: 2px solid #333; background: #1a1a1a;
         color: #aaa; font-size: 14px; font-weight: 700; cursor: pointer; text-align: center; transition: all 0.2s; }
  .tab.active { border-color: #FF6B1A; color: #FF6B1A; background: #1f1510; }
  .card { background: #1a1a1a; border-radius: 16px; padding: 22px; margin-bottom: 16px; display: none; }
  .card.active { display: block; }
  .card h2 { font-size: 15px; color: #FF6B1A; margin-bottom: 16px; font-weight: 700; }
  label { display: block; color: #aaa; font-size: 13px; margin-bottom: 5px; }
  input, select {
    width: 100%; background: #2a2a2a; border: 1px solid #333; border-radius: 10px;
    color: #fff; padding: 12px; font-size: 15px; margin-bottom: 14px; outline: none;
  }
  input:focus, select:focus { border-color: #FF6B1A; }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .btn { width: 100%; padding: 15px; border-radius: 12px; border: none; font-size: 16px;
         font-weight: 700; cursor: pointer; margin-bottom: 10px; transition: opacity 0.2s; }
  .btn:active { opacity: 0.8; }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-green { background: #00BB44; color: #fff; }
  .btn-orange { background: #FF6B1A; color: #fff; }
  .destinos { display: flex; gap: 10px; margin-bottom: 14px; }
  .destino { flex: 1; display: flex; align-items: center; gap: 8px; background: #2a2a2a;
             border: 2px solid #333; border-radius: 10px; padding: 10px 14px; cursor: pointer; }
  .destino.on { border-color: #00BB44; background: #0d2a0d; }
  .destino input[type=checkbox] { width: 18px; height: 18px; accent-color: #00BB44; cursor: pointer; }
  .destino span { font-size: 14px; font-weight: 600; }
  .wa-grupo { background:#2a2a2a; border:1px solid #333; border-radius:10px; padding:10px 14px; margin-bottom:14px; }
  .wa-grupo label { color:#aaa; font-size:12px; margin-bottom:6px; display:block; }
  .wa-grupo .opcoes { display:flex; gap:8px; flex-wrap:wrap; }
  .wa-grupo .op { flex:1; min-width:100px; display:flex; align-items:center; gap:6px; background:#1a1a1a; border:2px solid #333;
                  border-radius:8px; padding:8px 10px; cursor:pointer; font-size:13px; font-weight:600; color:#aaa; transition:all 0.2s; }
  .wa-grupo .op.on { border-color:#25D366; color:#25D366; background:#0d2a1a; }
  .wa-grupo .op input[type=checkbox] { width:16px; height:16px; accent-color:#25D366; cursor:pointer; }
  .msg { padding: 13px 16px; border-radius: 10px; margin-bottom: 14px; font-size: 14px; }
  .msg-ok  { background: #003d1a; color: #00ee66; border: 1px solid #00BB44; }
  .msg-err { background: #3d0000; color: #ff6666; border: 1px solid #ff4444; }
  .info { background: #1e2a1e; border: 1px solid #2a4a2a; border-radius: 10px;
          padding: 10px 14px; font-size: 13px; color: #88cc88; margin-bottom: 14px; }
  .loader { text-align: center; padding: 14px; color: #FF6B1A; font-size: 14px; display: none; }
  .login-wrap { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .login-box { background: #1a1a1a; border-radius: 20px; padding: 36px 28px; width: 340px; text-align: center; }
  .login-box .logo { font-size: 52px; margin-bottom: 8px; }
  .login-box h2 { color: #FF6B1A; font-size: 22px; margin-bottom: 4px; }
  .login-box p { color: #888; font-size: 13px; margin-bottom: 24px; }
</style>
</head>
<body>

{% if not logged_in %}
<div class="login-wrap">
  <div class="login-box">
    <div class="logo">👀</div>
    <h2>OlhaissoTech</h2>
    <p>Painel de Publicação</p>
    {% if error %}<div class="msg msg-err">{{ error }}</div>{% endif %}
    <form method="POST" action="/login">
      <input type="password" name="password" placeholder="Senha de acesso" autofocus>
      <button type="submit" class="btn btn-orange">Entrar</button>
    </form>
  </div>
</div>

{% else %}

<div class="header">
  <span>👀</span>
  <h1>OlhaissoTech — Publicação Manual</h1>
</div>

<div class="container">
  <div id="msg_area"></div>

  <div class="tabs">
    <div class="tab active" onclick="trocarAba('afiliado')">🔗 Link de Afiliado Pronto</div>
    <div class="tab" onclick="trocarAba('produto')">🛍️ Link de Produto</div>
    <div class="tab" onclick="trocarAba('busca')">🔍 Busca Induzida</div>
    <div class="tab" onclick="trocarAba('web')">🌐 Busca na Internet</div>
    <div class="tab" onclick="trocarAba('ml')">🔗 Gerar Link</div>
    <div class="tab" onclick="trocarAba('historico'); carregarHistorico()">📊 Histórico</div>
    <div class="tab" onclick="trocarAba('analytics'); carregarAnalytics()">📈 Analytics</div>
  </div>

  <!-- FLUXO 1: Link de afiliado pronto -->
  <div class="card active" id="card_afiliado">
    <h2>🔗 Publicar com link de afiliado pronto</h2>
    <div class="info">💡 Use para Amazon, Hotmart ou qualquer link já com afiliado gerado</div>

    <label>📎 Link de afiliado</label>
    <div style="display:flex; gap:10px; margin-bottom:14px;">
      <input type="url" id="af_link" placeholder="https://amzn.to/... ou qualquer link de afiliado" style="margin-bottom:0; flex:1;">
      <button onclick="abrirLink('af_link')" style="background:#2a2a2a; border:1px solid #444; border-radius:10px; color:#FF6B1A; font-size:22px; padding:0 16px; cursor:pointer;" title="Abrir em nova aba">🔗</button>
    </div>

    <label>📝 Nome do produto *</label>
    <input type="text" id="af_nome" placeholder="Ex: Fone Bluetooth JBL Tune 510BT">

    <div class="row2">
      <div>
        <label>💰 Preço atual (R$) *</label>
        <input type="number" id="af_preco" step="0.01" placeholder="Ex: 89.90">
      </div>
      <div>
        <label>💵 Preço original (R$)</label>
        <input type="number" id="af_preco_orig" step="0.01" placeholder="Ex: 149.90">
      </div>
    </div>

    <label>🏪 Loja</label>
    <select id="af_loja">
      <option value="AMAZON">Amazon</option>
      <option value="MERCADOLIVRE">Mercado Livre</option>
      <option value="SHOPEE">Shopee</option>
      <option value="ALIEXPRESS">AliExpress</option>
      <option value="OUTRO">Outro</option>
    </select>

    <label>🖼️ URL da imagem *</label>
    <input type="url" id="af_imagem" placeholder="Cole a URL da imagem do produto">

    <label>⭐ Texto em destaque (opcional)</label>
    <input type="text" id="af_destaque" placeholder="Ex: CAMPEÃO DE VENDAS, IMPERDÍVEL...">

    <label style="margin-bottom:8px;">📢 Publicar em:</label>
    <div class="destinos">
      <label class="destino on" id="dest_tg_af">
        <input type="checkbox" id="af_telegram" checked onchange="toggleDestino('dest_tg_af', this)">
        <span>✈️ Telegram</span>
      </label>
      <label class="destino on" id="dest_wa_af">
        <input type="checkbox" id="af_whatsapp" checked onchange="toggleDestino('dest_wa_af', this); document.getElementById('wa_grupo_af').style.display=this.checked?'block':'none';">
        <span>📱 WhatsApp</span>
      </label>
    </div>
    <div class="wa-grupo" id="wa_grupo_af">
      <label>📱 Grupo WhatsApp:</label>
      <div class="opcoes">
        <label class="op on" id="op_af_principal">
          <input type="checkbox" id="af_wa_principal" checked onchange="toggleGrupo('op_af_principal', this)">
          <span>👥 Principal</span>
        </label>
        <label class="op" id="op_af_teste">
          <input type="checkbox" id="af_wa_teste" onchange="toggleGrupo('op_af_teste', this)">
          <span>🧪 Teste</span>
        </label>
      </div>
    </div>

    <button class="btn btn-green" id="btn_af" onclick="publicarAfiliado()">📢 Publicar agora</button>
    <div class="loader" id="loader_af">⏳ Gerando imagem e publicando...</div>
  </div>

  <!-- FLUXO 2: Link de produto Shopee/AliExpress -->
  <div class="card" id="card_produto">
    <h2>🛍️ Publicar com link de produto (Shopee / AliExpress)</h2>
    <div class="info">💡 Cole o link do produto — nome e loja detectados automaticamente</div>

    <label>📎 Link do produto</label>
    <div style="display:flex; gap:10px; margin-bottom:14px;">
      <input type="url" id="pr_link" placeholder="https://shopee.com.br/... ou aliexpress.com/..." style="margin-bottom:0; flex:1;">
      <button onclick="abrirLink('pr_link')" style="background:#2a2a2a; border:1px solid #444; border-radius:10px; color:#FF6B1A; font-size:22px; padding:0 16px; cursor:pointer;" title="Abrir em nova aba">🔗</button>
    </div>

    <div class="row2">
      <div>
        <label>💰 Preço atual (R$) *</label>
        <input type="number" id="pr_preco" step="0.01" placeholder="Ex: 89.90">
      </div>
      <div>
        <label>💵 Preço original (R$)</label>
        <input type="number" id="pr_preco_orig" step="0.01" placeholder="Ex: 149.90">
      </div>
    </div>

    <label>🖼️ URL da imagem *</label>
    <input type="url" id="pr_imagem" placeholder="Cole a URL da imagem do produto">

    <label>⭐ Texto em destaque (opcional)</label>
    <input type="text" id="pr_destaque" placeholder="Ex: CAMPEÃO DE VENDAS, IMPERDÍVEL...">

    <label style="margin-bottom:8px;">📢 Publicar em:</label>
    <div class="destinos">
      <label class="destino on" id="dest_tg_pr">
        <input type="checkbox" id="pr_telegram" checked onchange="toggleDestino('dest_tg_pr', this)">
        <span>✈️ Telegram</span>
      </label>
      <label class="destino on" id="dest_wa_pr">
        <input type="checkbox" id="pr_whatsapp" checked onchange="toggleDestino('dest_wa_pr', this); document.getElementById('wa_grupo_pr').style.display=this.checked?'block':'none';">
        <span>📱 WhatsApp</span>
      </label>
    </div>
    <div class="wa-grupo" id="wa_grupo_pr">
      <label>📱 Grupo WhatsApp:</label>
      <div class="opcoes">
        <label class="op on" id="op_pr_principal">
          <input type="checkbox" id="pr_wa_principal" checked onchange="toggleGrupo('op_pr_principal', this)">
          <span>👥 Principal</span>
        </label>
        <label class="op" id="op_pr_teste">
          <input type="checkbox" id="pr_wa_teste" onchange="toggleGrupo('op_pr_teste', this)">
          <span>🧪 Teste</span>
        </label>
      </div>
    </div>

    <button class="btn btn-green" id="btn_pr" onclick="publicarProduto()">📢 Publicar agora</button>
    <div class="loader" id="loader_pr">⏳ Gerando imagem e publicando...</div>
  </div>

  <!-- FLUXO 3: Busca Induzida -->
  <div class="card" id="card_busca">
    <h2>🔍 Busca Induzida — Oferta Premium</h2>
    <div class="info">💡 Busca em Shopee + AliExpress com seus próprios filtros — ignora variáveis do Railway</div>

    <label>🔑 Palavra-chave *</label>
    <input type="text" id="bk_keyword" placeholder="Ex: monitor curvo, headset gamer, notebook...">

    <label>🏷️ Marca (opcional)</label>
    <input type="text" id="bk_marca" placeholder="Ex: DELL, ACER, INTEL, SAMSUNG... (opcional)">

    <label style="margin-bottom:8px;">🏪 Buscar em:</label>
    <div class="destinos" style="margin-bottom:14px;">

      <label class="destino on" id="dest_bk_shopee">
        <input type="checkbox" id="bk_usar_shopee" checked onchange="toggleDestino('dest_bk_shopee', this)">
        <span>🧡 Shopee</span>
      </label>
      <label class="destino on" id="dest_bk_ali">
        <input type="checkbox" id="bk_usar_ali" checked onchange="toggleDestino('dest_bk_ali', this)">
        <span>🛍️ AliExpress</span>
      </label>
    </div>

    <div class="row2">
      <div>
        <label>💰 Preço mínimo (R$) *</label>
        <input type="number" id="bk_preco_min" step="0.01" placeholder="Ex: 100">
      </div>
      <div>
        <label>💵 Preço máximo (R$) *</label>
        <input type="number" id="bk_preco_max" step="0.01" placeholder="Ex: 5000">
      </div>
    </div>

    <div class="row2">
      <div>
        <label>🏷️ Desconto mínimo (%) *</label>
        <input type="number" id="bk_desconto_min" step="1" min="0" max="99" placeholder="Ex: 20 (use 0 para sem limite)">
      </div>
      <div>
        <label>📦 Qtde de postagens *</label>
        <input type="number" id="bk_qtde" step="1" min="1" max="20" placeholder="Ex: 3" value="3">
      </div>
    </div>

    <label style="margin-bottom:8px;">📢 Publicar em:</label>
    <div class="destinos">
      <label class="destino on" id="dest_tg_bk">
        <input type="checkbox" id="bk_telegram" checked onchange="toggleDestino('dest_tg_bk', this)">
        <span>✈️ Telegram</span>
      </label>
      <label class="destino on" id="dest_wa_bk">
        <input type="checkbox" id="bk_whatsapp" checked onchange="toggleDestino('dest_wa_bk', this); document.getElementById('wa_grupo_bk').style.display=this.checked?'block':'none';">
        <span>📱 WhatsApp</span>
      </label>
    </div>
    <div class="wa-grupo" id="wa_grupo_bk">
      <label>📱 Grupo WhatsApp:</label>
      <div class="opcoes">
        <label class="op on" id="op_bk_principal">
          <input type="checkbox" id="bk_wa_principal" checked onchange="toggleGrupo('op_bk_principal', this)">
          <span>👥 Principal</span>
        </label>
        <label class="op" id="op_bk_teste">
          <input type="checkbox" id="bk_wa_teste" onchange="toggleGrupo('op_bk_teste', this)">
          <span>🧪 Teste</span>
        </label>
      </div>
    </div>

    <button class="btn btn-orange" id="btn_bk" onclick="buscarInduzido()">🔍 Buscar e publicar Oferta Premium</button>
    <div class="loader" id="loader_bk">⏳ Buscando ofertas...</div>
  </div>

  <!-- FLUXO 4: Busca na Internet -->
  <div class="card" id="card_web">
    <h2>🌐 Busca Livre na Internet</h2>
    <div class="info">💡 Busca no Google Shopping — traz preço, loja e imagem de cada produto</div>

    <label>🔑 O que você está procurando? *</label>
    <input type="text" id="wb_keyword" placeholder="Ex: fralda descartável, notebook Dell, iPhone 15..." onkeydown="if(event.key==='Enter') buscarInternet()">

    <label>💰 Preço máximo (R$) — opcional</label>
    <input type="number" id="wb_preco_max" step="0.01" placeholder="Ex: 2000 (deixe vazio para sem limite)" style="margin-bottom:14px;">

    <div class="row2">
      <div>
        <label>💵 Preço mínimo (R$) — opcional</label>
        <input type="number" id="wb_preco_min" step="0.01" placeholder="Ex: 500">
      </div>
      <div>
        <label>💰 Preço máximo (R$) — opcional</label>
        <input type="number" id="wb_preco_max" step="0.01" placeholder="Ex: 2000">
      </div>
    </div>

    <button class="btn" id="btn_wb" onclick="buscarInternet()" style="background:#0088cc;color:#fff;">🌐 Buscar agora</button>
    <div class="loader" id="loader_wb">⏳ Pesquisando no Google Shopping...</div>

    <div id="wb_resultados" style="margin-top:16px;"></div>
  </div>
  <!-- FLUXO 5: Gerador de Link ML Oficial -->
  <div class="card" id="card_ml">
    <h2>🔗 Gerar Link e Publicar (ML ou Amazon)</h2>
    <div class="info">💡 Cole o link do produto — detecta automaticamente se é ML ou Amazon e preenche os dados</div>

    <label>📎 Link do produto *</label>
    <div style="display:flex; gap:10px; margin-bottom:10px;">
      <input type="url" id="ml_link" placeholder="https://www.mercadolivre.com.br/... ou https://www.amazon.com.br/..." style="margin-bottom:0; flex:1;" oninput="detectarLojaInput()">
      <button onclick="abrirLink('ml_link')" style="background:#2a2a2a; border:1px solid #444; border-radius:10px; color:#FF6B1A; font-size:22px; padding:0 16px; cursor:pointer;" title="Abrir em nova aba">🔗</button>
    </div>

    <!-- Badge loja detectada -->
    <div id="ml_loja_badge" style="display:none;margin-bottom:10px;font-size:13px;font-weight:700;padding:6px 14px;border-radius:8px;width:fit-content;"></div>

    <button id="btn_ml_preencher" onclick="preencherDadosAuto()" style="width:100%;background:#1a3a5c;border:1px solid #0088cc;border-radius:10px;color:#4db8ff;font-size:14px;font-weight:700;padding:10px;cursor:pointer;margin-bottom:14px;">🔍 Preencher dados automaticamente</button>
    <div id="ml_preview" style="display:none;background:#111;border:1px solid #333;border-radius:12px;padding:12px;margin-bottom:14px;align-items:center;gap:12px;">
      <img id="ml_preview_img" src="" style="width:72px;height:72px;object-fit:contain;border-radius:8px;background:#222;flex-shrink:0;">
      <div style="flex:1;min-width:0;">
        <div id="ml_preview_nome" style="font-size:13px;font-weight:700;color:#fff;line-height:1.3;margin-bottom:4px;"></div>
        <div id="ml_preview_preco" style="font-size:14px;color:#FF6B1A;font-weight:800;"></div>
      </div>
    </div>

    <label>📝 Nome do produto *</label>
    <input type="text" id="ml_nome" placeholder="Ex: Smart TV Samsung 50 4K QLED">

    <div class="row2">
      <div>
        <label>💰 Preço atual (R$) *</label>
        <input type="number" id="ml_preco" step="0.01" placeholder="Ex: 1299.90">
      </div>
      <div>
        <label>💵 Preço original (R$)</label>
        <input type="number" id="ml_preco_orig" step="0.01" placeholder="Ex: 1999.90">
      </div>
    </div>

    <label>🖼️ URL da imagem *</label>
    <input type="url" id="ml_imagem" placeholder="Cole a URL da imagem do produto">

    <label>⭐ Texto em destaque (opcional)</label>
    <input type="text" id="ml_destaque" placeholder="Ex: OFERTA DO DIA, MAIS VENDIDO...">

    <label style="margin-bottom:8px;">📢 Publicar em:</label>
    <div class="destinos">
      <label class="destino on" id="dest_tg_ml">
        <input type="checkbox" id="ml_telegram" checked onchange="toggleDestino('dest_tg_ml', this)">
        <span>✈️ Telegram</span>
      </label>
      <label class="destino on" id="dest_wa_ml">
        <input type="checkbox" id="ml_whatsapp" checked onchange="toggleDestino('dest_wa_ml', this); document.getElementById('wa_grupo_ml').style.display=this.checked?'block':'none';">
        <span>📱 WhatsApp</span>
      </label>
    </div>
    <div class="wa-grupo" id="wa_grupo_ml">
      <label>📱 Grupo WhatsApp:</label>
      <div class="opcoes">
        <label class="op on" id="op_ml_principal">
          <input type="checkbox" id="ml_wa_principal" checked onchange="toggleGrupo('op_ml_principal', this)">
          <span>👥 Principal</span>
        </label>
        <label class="op" id="op_ml_teste">
          <input type="checkbox" id="ml_wa_teste" onchange="toggleGrupo('op_ml_teste', this)">
          <span>🧪 Teste</span>
        </label>
      </div>
    </div>

    <button class="btn" id="btn_ml" onclick="publicarAuto()" style="background:#FF6B1A;color:#fff;font-size:16px;">🚀 Gerar link e publicar</button>
    <div class="loader" id="loader_ml">⏳ Processando...</div>

    <div id="ml_resultado" style="margin-top:16px;"></div>
  </div>
  <!-- FLUXO 6: Histórico de postagens -->
  <div class="card" id="card_historico">
    <h2>📊 Histórico de Postagens</h2>
    <div class="info">💡 Últimos 100 produtos publicados pelo bot</div>

    <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:18px;margin-bottom:16px;">
      <h3 style="color:#FF6B1A;font-size:14px;margin-bottom:14px;">🎮 Disparar Ciclo Manual</h3>

      <div class="row2" style="margin-bottom:12px;">
        <div>
          <label>📦 Qtde de postagens</label>
          <input type="number" id="ciclo_qtde" value="4" min="1" max="20" step="1">
        </div>
        <div>
          <label>🏪 Lojas</label>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
            <label class="destino on" id="dest_ciclo_ml" style="flex:none;border-color:#FFE600;">
              <input type="checkbox" id="ciclo_ml" checked onchange="toggleDestino('dest_ciclo_ml',this)" style="accent-color:#FFE600;">
              <span style="font-size:12px;">🟡 ML</span>
            </label>
            <label class="destino on" id="dest_ciclo_shopee" style="flex:none;">
              <input type="checkbox" id="ciclo_shopee" checked onchange="toggleDestino('dest_ciclo_shopee',this)">
              <span style="font-size:12px;">🧡 Shopee</span>
            </label>
            <label class="destino on" id="dest_ciclo_ali" style="flex:none;">
              <input type="checkbox" id="ciclo_ali" checked onchange="toggleDestino('dest_ciclo_ali',this)">
              <span style="font-size:12px;">🛍️ Ali</span>
            </label>
            <label class="destino on" id="dest_ciclo_amazon" style="flex:none;border-color:#FF9900;">
              <input type="checkbox" id="ciclo_amazon" checked onchange="toggleDestino('dest_ciclo_amazon',this)" style="accent-color:#FF9900;">
              <span style="font-size:12px;">📦 Amazon</span>
            </label>
          </div>
        </div>
      </div>

      <label style="margin-bottom:8px;">📢 Publicar em:</label>
      <div class="destinos" style="margin-bottom:10px;">
        <label class="destino on" id="dest_ciclo_tg">
          <input type="checkbox" id="ciclo_telegram" checked onchange="toggleDestino('dest_ciclo_tg',this)">
          <span>✈️ Telegram</span>
        </label>
        <label class="destino on" id="dest_ciclo_wa_pri">
          <input type="checkbox" id="ciclo_wa_principal" checked onchange="toggleDestino('dest_ciclo_wa_pri',this)">
          <span>👥 WA Principal</span>
        </label>
        <label class="destino" id="dest_ciclo_wa_tst">
          <input type="checkbox" id="ciclo_wa_teste" onchange="toggleDestino('dest_ciclo_wa_tst',this)">
          <span>🧪 WA Teste</span>
        </label>
      </div>

      <button class="btn btn-orange" id="btn_ciclo" style="width:100%;margin-bottom:8px;" onclick="dispararCiclo()">🚀 Disparar Ciclo Agora</button>
      <div class="loader" id="loader_ciclo">⏳ Iniciando ciclo...</div>
      <button id="btn_ciclo_tb" style="width:100%;margin-top:4px;background:#1a3a1a;border:2px solid #00cc44;color:#00cc44;border-radius:12px;padding:14px;font-size:15px;font-weight:700;cursor:pointer;display:block;" onclick="dispararCicloTicketBaixo()">🤑 Disparar Ticket Baixo</button>
      <div class="loader" id="loader_ciclo_tb">⏳ Iniciando ciclo ticket baixo...</div>

      <!-- PAINEL DE LOG DOS BOTÕES -->
      <div id="ciclo_log_wrap" style="margin-top:14px;display:none;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <span style="color:#888;font-size:12px;font-weight:700;">📋 LOG DE DISPARO</span>
          <button onclick="limparLogCiclo()" style="background:none;border:1px solid #444;color:#666;border-radius:6px;padding:2px 8px;font-size:11px;cursor:pointer;">Limpar</button>
        </div>
        <div id="ciclo_log" style="background:#0a0a0a;border:1px solid #2a2a2a;border-radius:10px;padding:12px;font-family:monospace;font-size:12px;max-height:220px;overflow-y:auto;"></div>
      </div>
    </div>

    <div style="margin-top:20px;">
      <h3 style="color:#FF6B1A;font-size:14px;margin-bottom:12px;">📋 Histórico de Postagens</h3>
    </div>

    <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">
      <select id="hist_loja" onchange="carregarHistorico()" style="flex:1;min-width:120px;margin-bottom:0;">
        <option value="">Todas as lojas</option>
        <option value="MERCADOLIVRE">🟡 Mercado Livre</option>
        <option value="SHOPEE">🧡 Shopee</option>
        <option value="ALIEXPRESS">🛍️ AliExpress</option>
        <option value="AMAZON">📦 Amazon</option>
      </select>
      <button onclick="carregarHistorico()" style="background:#333;border:1px solid #555;color:#fff;border-radius:10px;padding:0 16px;cursor:pointer;font-size:14px;">🔄 Atualizar</button>
      <button onclick="limparHistorico()" style="background:#5a1a1a;border:1px solid #c0392b;color:#ff6b6b;border-radius:10px;padding:0 16px;cursor:pointer;font-size:14px;">🗑️ Limpar Histórico</button>
    </div>
    <div style="position:relative;margin-bottom:14px;">
      <input type="text" id="hist_busca" placeholder="🔍 Filtrar por nome do produto..."
        oninput="filtrarHistorico()"
        style="width:100%;background:#2a2a2a;border:1px solid #444;border-radius:10px;color:#fff;padding:11px 16px;font-size:14px;outline:none;">
      <button onclick="document.getElementById('hist_busca').value='';filtrarHistorico()"
        style="position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;color:#666;cursor:pointer;font-size:16px;" title="Limpar">✕</button>
    </div>
    <div id="hist_loader" style="text-align:center;color:#FF6B1A;padding:20px;display:none;">⏳ Carregando...</div>
    <div id="hist_area"></div>
  </div>
</div>

<script>
function copiarLink(btn) {
  const link = btn.dataset.link;
  navigator.clipboard.writeText(link).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✅ Copiado!';
    setTimeout(() => btn.textContent = orig, 2000);
  }).catch(() => {
    btn.textContent = '❌';
    setTimeout(() => btn.textContent = '📋', 2000);
  });
}

function trocarAba(aba) {
  const abas = ['afiliado', 'produto', 'busca', 'web', 'ml', 'historico'];
  document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', aba === abas[i]));
  abas.forEach(a => {
    const card = document.getElementById('card_' + a);
    if (card) card.classList.toggle('active', aba === a);
  });
  // Expande container para aba historico
  const cont = document.querySelector('.container');
  if (cont) cont.classList.toggle('wide', aba === 'historico');
}

function toggleDestino(id, checkbox) {
  document.getElementById(id).classList.toggle('on', checkbox.checked);
}

function toggleGrupo(id, checkbox) {
  document.getElementById(id).classList.toggle('on', checkbox.checked);
}

function getGruposWA(prefixo) {
  const principal = document.getElementById(prefixo + '_wa_principal')?.checked;
  const teste     = document.getElementById(prefixo + '_wa_teste')?.checked;
  return { wa_principal: principal || false, wa_teste: teste || false };
}

function abrirLink(inputId) {
  const url = document.getElementById(inputId).value.trim();
  if (!url) return alert("Cole o link primeiro!");
  window.open(url, '_blank');
}

function detectarLoja(url) {
  if (url.includes('aliexpress.com')) return 'ALIEXPRESS';
  if (url.includes('shopee.com.br'))  return 'SHOPEE';
  if (url.includes('amazon.com.br') || url.includes('amzn.to')) return 'AMAZON';
  return 'OUTRO';
}

function extrairNomeDaUrl(url) {
  try {
    const path = new URL(url).pathname;
    let slug = path.split('/').filter(Boolean)[0] || '';
    slug = slug.replace(/-i\.\d+\.\d+$/, '');
    slug = decodeURIComponent(slug).replace(/-/g, ' ');
    return slug.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ').trim();
  } catch(e) { return 'Produto em Oferta'; }
}

function mostrarMsg(html) {
  const area = document.getElementById('msg_area');
  area.innerHTML = html;
  setTimeout(() => area.innerHTML = '', 6000);
}

async function enviar(payload, btnId, loaderId, camposParaLimpar) {
  const btn = document.getElementById(btnId);
  btn.disabled = true;
  document.getElementById(loaderId).style.display = 'block';
  try {
    const resp = await fetch('/publicar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (data.ok) {
      mostrarMsg('<div class="msg msg-ok">✅ ' + data.msg + '</div>');
      camposParaLimpar.forEach(id => document.getElementById(id).value = '');
    } else {
      mostrarMsg(`<div class="msg msg-err">❌ Erro: ${data.erro}</div>`);
    }
  } catch(e) {
    mostrarMsg(`<div class="msg msg-err">❌ Erro: ${e.message}</div>`);
  } finally {
    btn.disabled = false;
    document.getElementById(loaderId).style.display = 'none';
  }
}

async function publicarAfiliado() {
  const link      = document.getElementById('af_link').value.trim();
  const nome      = document.getElementById('af_nome').value.trim();
  const preco     = parseFloat(document.getElementById('af_preco').value) || 0;
  const preco_orig= parseFloat(document.getElementById('af_preco_orig').value) || 0;
  const loja      = document.getElementById('af_loja').value;
  const imagem    = document.getElementById('af_imagem').value.trim();
  const destaque  = document.getElementById('af_destaque').value.trim();
  const telegram  = document.getElementById('af_telegram').checked;
  const whatsapp  = document.getElementById('af_whatsapp').checked;
  const grupos    = getGruposWA('af');

  if (!link)   return alert("Cole o link de afiliado!");
  if (!nome)   return alert("Preencha o nome do produto!");
  if (!preco)  return alert("Preencha o preço atual!");
  if (!imagem) return alert("Cole a URL da imagem!");
  if (!telegram && !whatsapp) return alert("Selecione ao menos um destino!");
  if (whatsapp && !grupos.wa_principal && !grupos.wa_teste) return alert("Selecione ao menos um grupo do WhatsApp!");

  await enviar(
    { nome, preco, preco_orig, loja, link, imagem, destaque, telegram, whatsapp, ...grupos },
    'btn_af', 'loader_af',
    ['af_link', 'af_nome', 'af_preco', 'af_preco_orig', 'af_imagem', 'af_destaque']
  );
}

async function publicarProduto() {
  const link      = document.getElementById('pr_link').value.trim();
  const preco     = parseFloat(document.getElementById('pr_preco').value) || 0;
  const preco_orig= parseFloat(document.getElementById('pr_preco_orig').value) || 0;
  const imagem    = document.getElementById('pr_imagem').value.trim();
  const destaque  = document.getElementById('pr_destaque').value.trim();
  const telegram  = document.getElementById('pr_telegram').checked;
  const whatsapp  = document.getElementById('pr_whatsapp').checked;
  const grupos    = getGruposWA('pr');

  if (!link)   return alert("Cole o link do produto!");
  if (!preco)  return alert("Preencha o preço atual!");
  if (!imagem) return alert("Cole a URL da imagem!");
  if (!telegram && !whatsapp) return alert("Selecione ao menos um destino!");
  if (whatsapp && !grupos.wa_principal && !grupos.wa_teste) return alert("Selecione ao menos um grupo do WhatsApp!");

  const btn = document.getElementById('btn_pr');
  btn.disabled = true;
  document.getElementById('loader_pr').style.display = 'block';
  document.getElementById('loader_pr').textContent = '⏳ Gerando link de afiliado...';

  try {
    const respLink = await fetch('/gerar_link', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ url: link })
    });
    const dataLink = await respLink.json();
    const linkFinal = dataLink.link || link;
    const loja = dataLink.loja || detectarLoja(link);
    const nome = extrairNomeDaUrl(link);

    document.getElementById('loader_pr').textContent = '⏳ Gerando imagem e publicando...';

    await enviar(
      { nome, preco, preco_orig, loja, link: linkFinal, imagem, destaque, telegram, whatsapp, ...grupos },
      'btn_pr', 'loader_pr',
      ['pr_link', 'pr_preco', 'pr_preco_orig', 'pr_imagem', 'pr_destaque']
    );
  } catch(e) {
    mostrarMsg(`<div class="msg msg-err">❌ Erro: ${e.message}</div>`);
    btn.disabled = false;
    document.getElementById('loader_pr').style.display = 'none';
  }
}

async function buscarInduzido() {
  const keyword      = document.getElementById('bk_keyword').value.trim();
  const marca        = document.getElementById('bk_marca').value.trim();
  const preco_min    = parseFloat(document.getElementById('bk_preco_min').value) || 0;
  const preco_max    = parseFloat(document.getElementById('bk_preco_max').value) || 0;
  const desconto_min = document.getElementById('bk_desconto_min').value;
  const qtde         = parseInt(document.getElementById('bk_qtde').value) || 3;
  const telegram     = document.getElementById('bk_telegram').checked;
  const whatsapp     = document.getElementById('bk_whatsapp').checked;
  const grupos       = getGruposWA('bk');
  const usar_ml      = false;
  const usar_shopee  = document.getElementById('bk_usar_shopee').checked;
  const usar_ali     = document.getElementById('bk_usar_ali').checked;

  if (!keyword)  return alert("Digite uma palavra-chave!");
  if (!usar_shopee && !usar_ali) return alert("Selecione ao menos uma loja!");
  if (!preco_min) return alert("Informe o preço mínimo!");
  if (!preco_max) return alert("Informe o preço máximo!");
  if (preco_max <= preco_min) return alert("Preço máximo deve ser maior que o mínimo!");
  if (desconto_min === '') return alert("Informe o desconto mínimo (use 0 para sem limite)!");
  if (!telegram && !whatsapp) return alert("Selecione ao menos um destino!");

  const keyword_final = marca ? `${keyword} ${marca}` : keyword;
  const lojas = [];
  if (usar_ml) lojas.push('ML');
  if (usar_shopee) lojas.push('Shopee');
  if (usar_ali) lojas.push('AliExpress');

  const btn = document.getElementById('btn_bk');
  btn.disabled = true;
  document.getElementById('loader_bk').style.display = 'block';
  document.getElementById('loader_bk').textContent = `⏳ Buscando ${qtde} oferta(s) em ${lojas.join(' + ')}...`;

  try {
    const resp = await fetch('/buscar_induzido', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ keyword: keyword_final, preco_min, preco_max, desconto_min: parseInt(desconto_min),
        qtde, usar_ml, usar_shopee, usar_ali, telegram, whatsapp, ...grupos })
    });
    const data = await resp.json();
    if (data.ok) {
      mostrarMsg(`<div class="msg msg-ok">✅ ${data.msg}</div>`);
      document.getElementById('bk_keyword').value = '';
      document.getElementById('bk_marca').value = '';
      document.getElementById('bk_preco_min').value = '';
      document.getElementById('bk_preco_max').value = '';
      document.getElementById('bk_desconto_min').value = '';
      document.getElementById('bk_qtde').value = '3';
    } else {
      mostrarMsg(`<div class="msg msg-err">❌ Erro: ${data.erro}</div>`);
    }
  } catch(e) {
    mostrarMsg(`<div class="msg msg-err">❌ Erro: ${e.message}</div>`);
  } finally {
    btn.disabled = false;
    document.getElementById('loader_bk').style.display = 'none';
  }
}

function detectarLojaInput() {
  const link = document.getElementById('ml_link').value.trim();
  const badge = document.getElementById('ml_loja_badge');
  if (!badge) return;
  if (link.includes('mercadolivre.com.br') || link.includes('meli.la')) {
    badge.style.display = 'block';
    badge.style.background = '#1a3a1a';
    badge.style.color = '#FFE600';
    badge.style.border = '1px solid #FFE600';
    badge.textContent = '🟡 Mercado Livre detectado';
  } else if (link.includes('amazon.com.br') || link.includes('amzn.to')) {
    badge.style.display = 'block';
    badge.style.background = '#1a2a3a';
    badge.style.color = '#FF9900';
    badge.style.border = '1px solid #FF9900';
    badge.textContent = '📦 Amazon detectada';
  } else {
    badge.style.display = 'none';
  }
}

async function preencherDadosAuto() {
  const link = document.getElementById('ml_link').value.trim();
  if (!link) return alert("Cole o link do produto primeiro!");

  const isML     = link.includes('mercadolivre.com.br') || link.includes('meli.la');
  const isAmazon = link.includes('amazon.com.br') || link.includes('amzn.to');

  if (!isML && !isAmazon) return alert("Cole um link do Mercado Livre ou da Amazon!");

  const btn = document.getElementById('btn_ml_preencher');
  btn.disabled = true;
  btn.textContent = "⏳ Buscando dados...";

  try {
    const endpoint = isAmazon ? '/dados_produto_amazon' : '/dados_produto_ml';
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ url: link })
    });
    const data = await resp.json();
    if (!data.ok) { alert('Erro: ' + data.erro); return; }

    if (data.nome)       document.getElementById('ml_nome').value = data.nome;
    if (data.preco)      document.getElementById('ml_preco').value = data.preco;
    if (data.preco_orig) document.getElementById('ml_preco_orig').value = data.preco_orig;
    if (data.imagem)     document.getElementById('ml_imagem').value = data.imagem;

    if (data.imagem || data.nome) {
      const preview = document.getElementById('ml_preview');
      preview.style.display = 'flex';
      if (data.imagem) document.getElementById('ml_preview_img').src = data.imagem;
      if (data.nome)   document.getElementById('ml_preview_nome').textContent = data.nome;
      if (data.preco) {
        const orig = data.preco_orig ? ' (de R$ ' + data.preco_orig + ')' : '';
        document.getElementById('ml_preview_preco').textContent = 'R$ ' + data.preco + orig;
      }
    }
    btn.textContent = "✅ Dados preenchidos!";
    setTimeout(() => { btn.textContent = "🔍 Preencher dados automaticamente"; }, 3000);
  } catch(e) {
    alert('Erro ao buscar dados: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function publicarAuto() {
  const link      = document.getElementById('ml_link').value.trim();
  const nome      = document.getElementById('ml_nome').value.trim();
  const preco     = parseFloat(document.getElementById('ml_preco').value) || 0;
  const preco_orig= parseFloat(document.getElementById('ml_preco_orig').value) || 0;
  const imagem    = document.getElementById('ml_imagem').value.trim();
  const destaque  = document.getElementById('ml_destaque').value.trim();
  const telegram  = document.getElementById('ml_telegram').checked;
  const whatsapp  = document.getElementById('ml_whatsapp').checked;
  const grupos    = getGruposWA('ml');

  const isML     = link.includes('mercadolivre.com.br') || link.includes('meli.la');
  const isAmazon = link.includes('amazon.com.br') || link.includes('amzn.to');

  if (!link)               return alert("Cole o link do produto!");
  if (!isML && !isAmazon)  return alert("Use um link do Mercado Livre ou da Amazon!");
  if (!nome)               return alert("Preencha o nome do produto!");
  if (!preco)              return alert("Preencha o preco atual!");
  if (!imagem)             return alert("Cole a URL da imagem!");
  if (!telegram && !whatsapp) return alert("Selecione ao menos um destino!");
  if (whatsapp && !grupos.wa_principal && !grupos.wa_teste) return alert("Selecione ao menos um grupo do WhatsApp!");

  const btn = document.getElementById('btn_ml');
  const loader = document.getElementById('loader_ml');
  const resultado = document.getElementById('ml_resultado');
  btn.disabled = true;
  loader.style.display = 'block';
  resultado.innerHTML = '';

  try {
    let linkFinal = link;
    let loja = isAmazon ? 'AMAZON' : 'MERCADOLIVRE';

    if (isML) {
      loader.textContent = "⏳ Gerando link meli.la...";
      const respLink = await fetch('/gerar_link_ml', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ url: link })
      });
      const dataLink = await respLink.json();
      if (!dataLink.ok) {
        resultado.innerHTML = `<div class="msg msg-err">❌ ${dataLink.erro}</div>`;
        return;
      }
      linkFinal = dataLink.link;
    } else {
      // Amazon — adiciona tag de afiliado se não tiver, depois encurta
      let linkComTag = link;
      if (!link.includes('olhaissotech-20')) {
        const sep = link.includes('?') ? '&' : '?';
        linkComTag = link + sep + 'tag=olhaissotech-20';
      }
      loader.textContent = "⏳ Encurtando link Amazon...";
      try {
        const respEnc = await fetch('/encurtar_link', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ url: linkComTag })
        });
        const dataEnc = await respEnc.json();
        linkFinal = dataEnc.ok ? dataEnc.link : linkComTag;
      } catch(e) {
        linkFinal = linkComTag; // fallback: link longo
      }
    }

    loader.textContent = "⏳ Gerando imagem e publicando...";
    const respPub = await fetch('/publicar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ nome, preco, preco_orig, loja, link: linkFinal, imagem, destaque, telegram, whatsapp, ...grupos })
    });
    const dataPub = await respPub.json();

    if (dataPub.ok) {
      const corLink = isAmazon ? '#FF9900' : '#FFE600';
      const icone   = isAmazon ? '📦' : '🟡';
      resultado.innerHTML = `
        <div class="msg msg-ok">
          ✅ ${dataPub.msg}<br><br>
          <strong>${icone} Link gerado:</strong><br>
          <a href="${linkFinal}" target="_blank" style="color:${corLink};word-break:break-all;">${linkFinal}</a><br><br>
          <button onclick="copiarLink(this)"
            data-link="${linkFinal}"
            style="background:#2a2a2a;border:1px solid #555;color:#fff;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:14px;">
            📋 Copiar link
          </button>
        </div>`;
      ['ml_link','ml_nome','ml_preco','ml_preco_orig','ml_imagem','ml_destaque'].forEach(id => document.getElementById(id).value = '');
      document.getElementById('ml_preview').style.display = 'none';
      document.getElementById('ml_loja_badge').style.display = 'none';
    } else {
      resultado.innerHTML = `<div class="msg msg-err">❌ ${dataPub.erro}</div>`;
    }
  } catch(e) {
    resultado.innerHTML = `<div class="msg msg-err">❌ Erro: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    loader.style.display = 'none';
    loader.textContent = "⏳ Processando...";
  }
}

// Mantém alias para compatibilidade
async function preencherDadosML() { return preencherDadosAuto(); }
async function publicarML() { return publicarAuto(); }

let _histRows = [];
let _histSort = { col: 'postado_em', asc: false };

function filtrarHistorico() {
  const busca = (document.getElementById('hist_busca')?.value || '').toLowerCase().trim();
  let rows = busca ? _histRows.filter(r => r.nome && r.nome.toLowerCase().includes(busca)) : [..._histRows];
  rows = ordenarRows(rows);
  renderHistorico(rows);
}

function ordenarRows(rows) {
  const { col, asc } = _histSort;
  return [...rows].sort((a, b) => {
    let va = a[col] ?? '', vb = b[col] ?? '';
    if (col === 'preco') { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
    if (va < vb) return asc ? -1 : 1;
    if (va > vb) return asc ? 1 : -1;
    return 0;
  });
}

function sortBy(col) {
  if (_histSort.col === col) {
    _histSort.asc = !_histSort.asc;
  } else {
    _histSort.col = col;
    _histSort.asc = col === 'nome';
  }
  filtrarHistorico();
}

function renderHistorico(rows) {
  const area = document.getElementById('hist_area');
  if (!area) return;

  const lojaEmoji = { MERCADOLIVRE: '🟡', SHOPEE: '🧡', ALIEXPRESS: '🛍️', AMAZON: '📦' };

  function fmtData(dt) {
    if (!dt) return '-';
    const d = dt.replace('T', ' ');
    const parts = d.substring(0, 16).split(' ');
    const ymd = parts[0].split('-');
    return ymd[2] + '/' + ymd[1] + '/' + ymd[0].substring(2) + ' ' + (parts[1] || '');
  }

  function fmtPreco(v) {
    if (!v) return '-';
    return 'R$ ' + parseFloat(v).toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2});
  }

  function thSort(label, col, align) {
    const ico = _histSort.col === col ? (_histSort.asc ? ' ▲' : ' ▼') : ' ⇅';
    const th = document.createElement('th');
    th.setAttribute('onclick', 'sortBy("' + col + '")');
    th.style.cssText = 'text-align:' + align + ';padding:10px 8px;font-weight:700;white-space:nowrap;cursor:pointer;user-select:none;';
    th.title = 'Ordenar por ' + label;
    th.innerHTML = label + '<span style="font-size:10px;opacity:0.7;">' + ico + '</span>';
    return th.outerHTML;
  }

  if (!rows || rows.length === 0) {
    area.innerHTML = '<div class="info">Nenhum registro encontrado.</div>';
    return;
  }

  let html = '<div style="font-size:12px;color:#888;margin-bottom:8px;">' + rows.length + ' registro(s)</div>';
  html += '<div style="overflow-x:auto;border-radius:10px;border:1px solid #2a2a2a;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
  html += '<thead><tr style="background:#222;color:#FF6B1A;border-bottom:2px solid #333;">';
  html += thSort('Produto', 'nome', 'left');
  html += thSort('Loja', 'loja', 'center');
  html += thSort('Preço', 'preco', 'right');
  html += thSort('Origem', 'origem', 'center');
  html += '<th style="text-align:center;padding:10px 8px;font-weight:700;white-space:nowrap;">Link</th>';
  html += thSort('Data', 'postado_em', 'right');
  html += '</tr></thead><tbody>';

  rows.forEach((r, i) => {
    const bg = i % 2 === 0 ? '#1a1a1a' : '#141414';
    const emoji = lojaEmoji[r.loja] || '🏪';
    const origemBadge = r.origem === 'WEB'
      ? '<span style="background:#1a3a5c;color:#4db8ff;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;">🌐 WEB</span>'
      : '<span style="background:#1a2a1a;color:#00cc44;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;">🤖 BOT</span>';
    const linkBtn = r.link
      ? '<a href="' + r.link + '" target="_blank" style="background:#2a2a2a;border:1px solid #444;color:#FF6B1A;padding:4px 10px;border-radius:6px;font-size:12px;text-decoration:none;white-space:nowrap;">🔗 Abrir</a>'
      : '<span style="color:#555;font-size:12px;">—</span>';
    html += '<tr style="background:' + bg + ';border-bottom:1px solid #222;">';
    html += '<td style="padding:10px 8px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff;" title="' + r.nome + '">' + r.nome + '</td>';
    html += '<td style="padding:10px 8px;text-align:center;white-space:nowrap;">' + emoji + ' ' + (r.loja || '-') + '</td>';
    html += '<td style="padding:10px 8px;text-align:right;color:#FF6B1A;font-weight:700;white-space:nowrap;">' + fmtPreco(r.preco) + '</td>';
    html += '<td style="padding:10px 8px;text-align:center;">' + origemBadge + '</td>';
    html += '<td style="padding:10px 8px;text-align:center;">' + linkBtn + '</td>';
    html += '<td style="padding:10px 8px;text-align:right;color:#888;white-space:nowrap;font-size:12px;">' + fmtData(r.postado_em) + '</td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  area.innerHTML = html;
}

// ── Utilitários de log visual ──────────────────────────────────────────────
function _logCiclo(tipo, msg, dados) {
  const wrap = document.getElementById('ciclo_log_wrap');
  const box  = document.getElementById('ciclo_log');
  if (!wrap || !box) return;
  wrap.style.display = 'block';
  const cores = { INFO: '#888', PAYLOAD: '#4db8ff', OK: '#00cc44', ERRO: '#ff4444', HTTP: '#FFE600' };
  const cor = cores[tipo] || '#ccc';
  const ts  = new Date().toLocaleTimeString('pt-BR');
  let linha = `<div style="margin-bottom:4px;"><span style="color:#555;">[${ts}]</span> <span style="color:${cor};font-weight:700;">[${tipo}]</span> <span style="color:#ccc;">${msg}</span>`;
  if (dados !== undefined) {
    linha += `<br><span style="color:#666;padding-left:16px;">${JSON.stringify(dados, null, 0)}</span>`;
  }
  linha += '</div>';
  box.innerHTML += linha;
  box.scrollTop = box.scrollHeight;
  // Espelha no console do navegador também
  console.log(`[OLHAISSO][${tipo}]`, msg, dados !== undefined ? dados : '');
}

function limparLogCiclo() {
  const box = document.getElementById('ciclo_log');
  if (box) box.innerHTML = '';
  const wrap = document.getElementById('ciclo_log_wrap');
  if (wrap) wrap.style.display = 'none';
}
// ────────────────────────────────────────────────────────────────────────────

async function dispararCicloTicketBaixo() {
  const telegram     = document.getElementById('ciclo_telegram').checked;
  const wa_principal = document.getElementById('ciclo_wa_principal').checked;
  const wa_teste     = document.getElementById('ciclo_wa_teste').checked;
  const qtde         = parseInt(document.getElementById('ciclo_qtde').value) || 4;

  _logCiclo('INFO', '🤑 Botão TICKET BAIXO clicado');
  _logCiclo('PAYLOAD', 'Payload que será enviado para /disparar_ciclo_tb', { telegram, wa_principal, wa_teste, qtde });

  if (!telegram && !wa_principal && !wa_teste) {
    _logCiclo('ERRO', 'Nenhum canal selecionado — abortando');
    return alert("Selecione ao menos um canal!");
  }

  const btn = document.getElementById('btn_ciclo_tb');
  btn.disabled = true;
  document.getElementById('loader_ciclo_tb').style.display = 'block';

  try {
    _logCiclo('HTTP', 'POST /disparar_ciclo_tb → aguardando resposta...');
    const resp = await fetch('/disparar_ciclo_tb', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ telegram, wa_principal, wa_teste, qtde })
    });
    _logCiclo('HTTP', 'Resposta recebida', { status: resp.status, ok: resp.ok });
    const data = await resp.json();
    _logCiclo('HTTP', 'Body da resposta', data);
    if (data.ok) {
      _logCiclo('OK', '✅ Ciclo ticket baixo iniciado: ' + (data.msg || ''));
      mostrarMsg('<div class="msg msg-ok">🤑 ' + data.msg + '</div>');
    } else {
      _logCiclo('ERRO', '❌ Retorno de erro do bot: ' + (data.erro || 'desconhecido'));
      mostrarMsg('<div class="msg msg-err">❌ ' + data.erro + '</div>');
    }
  } catch(e) {
    _logCiclo('ERRO', '❌ Exceção JS ao chamar /disparar_ciclo_tb: ' + e.message);
    mostrarMsg('<div class="msg msg-err">❌ Erro: ' + e.message + '</div>');
  } finally {
    btn.disabled = false;
    document.getElementById('loader_ciclo_tb').style.display = 'none';
  }
}

async function dispararCiclo() {
  const qtde         = parseInt(document.getElementById('ciclo_qtde').value) || 4;
  const telegram     = document.getElementById('ciclo_telegram').checked;
  const wa_principal = document.getElementById('ciclo_wa_principal').checked;
  const wa_teste     = document.getElementById('ciclo_wa_teste').checked;
  const usar_ml      = document.getElementById('ciclo_ml').checked;
  const usar_shopee  = document.getElementById('ciclo_shopee').checked;
  const usar_ali     = document.getElementById('ciclo_ali').checked;
  const usar_amazon  = document.getElementById('ciclo_amazon').checked;

  _logCiclo('INFO', '🚀 Botão CICLO NORMAL clicado');
  _logCiclo('PAYLOAD', 'Payload que será enviado para /disparar_ciclo', { qtde, telegram, wa_principal, wa_teste, usar_ml, usar_shopee, usar_ali, usar_amazon });

  if (!telegram && !wa_principal && !wa_teste) {
    _logCiclo('ERRO', 'Nenhum canal selecionado — abortando');
    return alert("Selecione ao menos um canal!");
  }
  if (!usar_ml && !usar_shopee && !usar_ali && !usar_amazon) {
    _logCiclo('ERRO', 'Nenhuma loja selecionada — abortando');
    return alert("Selecione ao menos uma loja!");
  }

  const btn = document.getElementById('btn_ciclo');
  btn.disabled = true;
  document.getElementById('loader_ciclo').style.display = 'block';

  try {
    _logCiclo('HTTP', 'POST /disparar_ciclo → aguardando resposta...');
    const resp = await fetch('/disparar_ciclo', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ qtde, telegram, wa_principal, wa_teste, usar_ml, usar_shopee, usar_ali, usar_amazon })
    });
    _logCiclo('HTTP', 'Resposta recebida', { status: resp.status, ok: resp.ok });
    const data = await resp.json();
    _logCiclo('HTTP', 'Body da resposta', data);
    if (data.ok) {
      _logCiclo('OK', '✅ Ciclo iniciado: ' + (data.msg || ''));
      mostrarMsg('<div class="msg msg-ok">🚀 ' + data.msg + '</div>');
    } else {
      _logCiclo('ERRO', '❌ Retorno de erro do bot: ' + (data.erro || 'desconhecido'));
      mostrarMsg('<div class="msg msg-err">❌ ' + data.erro + '</div>');
    }
  } catch(e) {
    _logCiclo('ERRO', '❌ Exceção JS ao chamar /disparar_ciclo: ' + e.message);
    mostrarMsg('<div class="msg msg-err">❌ Erro: ' + e.message + '</div>');
  } finally {
    btn.disabled = false;
    document.getElementById('loader_ciclo').style.display = 'none';
  }
}

async function limparHistorico() {
  if (!confirm("Tem certeza que deseja limpar TODO o historico? Produtos ja postados poderao ser repostados.")) return;
  try {
    const resp = await fetch('/limpar_historico', { method: 'POST' });
    const data = await resp.json();
    if (data.ok) {
      alert('✅ Historico limpo! ' + data.msg);
      carregarHistorico();
    } else {
      alert('❌ Erro: ' + (data.erro || 'desconhecido'));
    }
  } catch (e) {
    alert('❌ Erro ao limpar: ' + e.message);
  }
}

async function carregarHistorico() {
  const loja = document.getElementById('hist_loja')?.value || '';
  const area = document.getElementById('hist_area');
  const loader = document.getElementById('hist_loader');
  if (!area) return;
  loader.style.display = 'block';
  area.innerHTML = '';

  try {
    const BOT_URL = window.location.origin.replace('-web-', '-') + '/historico';
    const resp = await fetch('/historico_proxy?loja=' + encodeURIComponent(loja));
    const data = await resp.json();

    if (!data.ok) {
      area.innerHTML = '<div class="msg msg-err">❌ ' + (data.erro || 'Erro ao carregar') + '</div>';
      return;
    }

    _histRows = data.rows || [];
    document.getElementById('hist_busca').value = '';
    renderHistorico(_histRows);
  } catch(e) {
    area.innerHTML = '<div class="msg msg-err">❌ Erro: ' + e.message + '</div>';
  } finally {
    loader.style.display = 'none';
  }
}

async function buscarInternet() {
  const keyword   = document.getElementById('wb_keyword').value.trim();
  const preco_min = parseFloat(document.getElementById('wb_preco_min').value) || 0;
  const preco_max = parseFloat(document.getElementById('wb_preco_max').value) || 0;

  if (!keyword) return alert("Digite o que está procurando!");

  const btn = document.getElementById('btn_wb');
  btn.disabled = true;
  document.getElementById('loader_wb').style.display = 'block';
  document.getElementById('wb_resultados').innerHTML = '';

  try {
    const resp = await fetch('/buscar_internet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ keyword, preco_min, preco_max })
    });
    const data = await resp.json();
    const area = document.getElementById('wb_resultados');

    if (data.ok && data.resultados && data.resultados.length > 0) {
      let html = `<div style="color:#aaa;font-size:13px;margin-bottom:12px;">✅ ${data.resultados.length} produtos encontrados no Google Shopping</div>`;
      data.resultados.forEach((r) => {
        const linkSafe = r.link.replace(/'/g, "\\'");
        html += `
        <div style="background:#222;border-radius:12px;padding:12px;margin-bottom:10px;border:1px solid #333;display:flex;gap:12px;align-items:flex-start;">
          ${r.imagem ? `<img src="${r.imagem}" style="width:64px;height:64px;object-fit:contain;border-radius:8px;background:#333;flex-shrink:0;">` : ''}
          <div style="flex:1;min-width:0;">
            <div style="font-size:13px;font-weight:700;color:#fff;margin-bottom:4px;line-height:1.3;">${r.nome}</div>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
              ${r.preco ? `<span style="color:#FF6B1A;font-weight:800;font-size:15px;">${r.preco}</span>` : ''}
              ${r.preco_orig ? `<span style="color:#666;font-size:12px;text-decoration:line-through;">${r.preco_orig}</span>` : ''}
              ${r.desconto > 0 ? `<span style="background:#00BB44;color:#fff;padding:2px 7px;border-radius:6px;font-size:12px;font-weight:700;">-${r.desconto}%</span>` : ''}
              ${r.loja  ? `<span style="color:#aaa;font-size:12px;">🏪 ${r.loja}</span>` : ''}
            </div>
            <div style="display:flex;gap:6px;">
              <button onclick="copiarLink(this)" data-link="${linkSafe}" 
                style="background:#0088cc;color:#fff;border:none;border-radius:8px;padding:7px 12px;cursor:pointer;font-size:14px;font-weight:700;">
                📋 Copiar
              </button>
              <a href="${r.link}" target="_blank"
                style="background:#333;color:#fff;border-radius:8px;padding:7px 12px;font-size:14px;text-decoration:none;display:inline-block;font-weight:700;">
                🔗 Abrir
              </a>
            </div>
          </div>
        </div>`;
      });
      area.innerHTML = html;
    } else {
      area.innerHTML = `<div class="msg msg-err">❌ ${data.erro || 'Nenhum resultado encontrado'}</div>`;
    }
  } catch(e) {
    document.getElementById('wb_resultados').innerHTML = `<div class="msg msg-err">❌ Erro: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    document.getElementById('loader_wb').style.display = 'none';
  }
}

async function carregarAnalytics() {
  const loader = document.getElementById('analytics_loader');
  if (loader) loader.style.display = 'block';
  try {
    const resp = await fetch('/historico_proxy');
    const data = await resp.json();
    if (!data.ok || !data.rows) { if(loader) loader.textContent='Erro ao carregar dados.'; return; }
    if (loader) loader.style.display = 'none';
    const rows = data.rows;
    const hoje = new Date().toISOString().slice(0,10);

    const total = rows.length;
    const hoje_rows = rows.filter(r => r.postado_em && r.postado_em.startsWith(hoje));
    const total_hoje = hoje_rows.length;
    const lojas_unicas = [...new Set(rows.map(r => r.loja))].length;
    const precos = rows.filter(r => r.preco > 0).map(r => r.preco);
    const preco_medio = precos.length ? (precos.reduce((a,b)=>a+b,0)/precos.length).toFixed(2) : 0;

    document.getElementById('analytics_kpis').innerHTML = [
      { label:'Total registros', valor:total, cor:'#FF6B1A', icone:'📦' },
      { label:'Posts hoje', valor:total_hoje, cor:'#00bb44', icone:'📅' },
      { label:'Lojas ativas', valor:lojas_unicas, cor:'#00aaff', icone:'🏪' },
      { label:'Preço médio', valor:'R$ '+String(preco_medio).replace('.',','), cor:'#FFE600', icone:'💰' },
    ].map(k=>`<div style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;padding:14px;text-align:center;">
      <div style="font-size:22px;margin-bottom:4px;">${k.icone}</div>
      <div style="font-size:22px;font-weight:700;color:${k.cor};">${k.valor}</div>
      <div style="font-size:11px;color:#888;margin-top:2px;">${k.label}</div>
    </div>`).join('');

    const por_loja = {};
    rows.forEach(r => { por_loja[r.loja]=(por_loja[r.loja]||0)+1; });
    const max_loja = Math.max(...Object.values(por_loja),1);
    const cores_loja = {MERCADOLIVRE:'#FFE600',AMAZON:'#FF9900',ALIEXPRESS:'#FF4500',SHOPEE:'#FF6600'};
    document.getElementById('analytics_lojas').innerHTML = Object.entries(por_loja).sort((a,b)=>b[1]-a[1]).map(([loja,qtd])=>{
      const pct=Math.round(qtd/total*100), cor=cores_loja[loja]||'#888', barra=Math.round(qtd/max_loja*100);
      return `<div><div style="display:flex;justify-content:space-between;margin-bottom:4px;"><span style="color:#ccc;font-size:13px;">${loja}</span><span style="color:${cor};font-size:13px;font-weight:700;">${qtd} posts (${pct}%)</span></div><div style="background:#2a2a2a;border-radius:6px;height:8px;"><div style="background:${cor};width:${barra}%;height:8px;border-radius:6px;"></div></div></div>`;
    }).join('') || '<span style="color:#666;">Sem dados</span>';

    const por_hora = {};
    hoje_rows.forEach(r => { if(!r.postado_em)return; const h=r.postado_em.substring(11,13)+'h'; por_hora[h]=(por_hora[h]||0)+1; });
    const max_hora = Math.max(...Object.values(por_hora),1);
    document.getElementById('analytics_horarios').innerHTML = Object.entries(por_hora).sort().map(([hora,qtd])=>{
      const barra=Math.round(qtd/max_hora*100);
      return `<div><div style="display:flex;justify-content:space-between;margin-bottom:3px;"><span style="color:#ccc;font-size:12px;">🕐 ${hora}</span><span style="color:#FF6B1A;font-size:12px;font-weight:700;">${qtd} post(s)</span></div><div style="background:#2a2a2a;border-radius:4px;height:6px;"><div style="background:#FF6B1A;width:${barra}%;height:6px;border-radius:4px;"></div></div></div>`;
    }).join('') || '<span style="color:#666;">Nenhum post hoje ainda</span>';

    const por_nome = {};
    rows.forEach(r => { por_nome[r.nome]=(por_nome[r.nome]||0)+1; });
    document.getElementById('analytics_top_produtos').innerHTML = Object.entries(por_nome).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([nome,qtd],i)=>`
      <div style="display:flex;align-items:center;gap:10px;padding:8px;background:#1a1a1a;border-radius:8px;">
        <span style="color:#FF6B1A;font-weight:700;font-size:16px;min-width:24px;">#${i+1}</span>
        <span style="color:#ccc;font-size:12px;flex:1;line-height:1.4;">${nome?nome.substring(0,60)+(nome.length>60?'...':''):'-'}</span>
        <span style="color:#00bb44;font-weight:700;font-size:13px;white-space:nowrap;">${qtd}x</span>
      </div>`).join('') || '<span style="color:#666;">Sem dados</span>';

    const por_origem = {};
    rows.forEach(r => { const o=r.origem||'BOT'; por_origem[o]=(por_origem[o]||0)+1; });
    const max_orig = Math.max(...Object.values(por_origem),1);
    const cores_orig = {BOT:'#00bb44',WEB:'#00aaff',WEB_MANUAL:'#FF6B1A'};
    document.getElementById('analytics_origens').innerHTML = Object.entries(por_origem).sort((a,b)=>b[1]-a[1]).map(([orig,qtd])=>{
      const pct=Math.round(qtd/total*100), cor=cores_orig[orig]||'#888', barra=Math.round(qtd/max_orig*100);
      return `<div><div style="display:flex;justify-content:space-between;margin-bottom:4px;"><span style="color:#ccc;font-size:13px;">${orig}</span><span style="color:${cor};font-size:13px;font-weight:700;">${qtd} (${pct}%)</span></div><div style="background:#2a2a2a;border-radius:6px;height:8px;"><div style="background:${cor};width:${barra}%;height:8px;border-radius:6px;"></div></div></div>`;
    }).join('') || '<span style="color:#666;">Sem dados</span>';

  } catch(e) {
    if(loader) loader.textContent='Erro: '+e.message;
    else console.error(e);
  }
}
</script>

  <!-- FLUXO 7: Analytics -->
  <div class="card" id="card_analytics" style="display:none;">
    <h2>📈 Analytics</h2>
    <div class="info">💡 Dashboard baseado nos últimos 100 posts registrados no banco</div>

    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;">
      <button onclick="carregarAnalytics()" style="background:#333;border:1px solid #555;color:#fff;border-radius:10px;padding:8px 18px;cursor:pointer;font-size:14px;">🔄 Atualizar</button>
    </div>

    <div id="analytics_kpis" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px;"></div>

    <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:16px;margin-bottom:14px;">
      <h3 style="color:#FF6B1A;font-size:13px;margin-bottom:14px;">🏪 Posts por Loja</h3>
      <div id="analytics_lojas" style="display:flex;flex-direction:column;gap:8px;"></div>
    </div>

    <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:16px;margin-bottom:14px;">
      <h3 style="color:#FF6B1A;font-size:13px;margin-bottom:14px;">⏰ Posts por Horário (últimas 24h)</h3>
      <div id="analytics_horarios" style="display:flex;flex-direction:column;gap:6px;"></div>
    </div>

    <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:16px;margin-bottom:14px;">
      <h3 style="color:#FF6B1A;font-size:13px;margin-bottom:14px;">🏆 Produtos mais postados</h3>
      <div id="analytics_top_produtos" style="display:flex;flex-direction:column;gap:6px;"></div>
    </div>

    <div style="background:#111;border:1px solid #2a2a2a;border-radius:14px;padding:16px;">
      <h3 style="color:#FF6B1A;font-size:13px;margin-bottom:14px;">🤖 Origem dos Posts</h3>
      <div id="analytics_origens" style="display:flex;flex-direction:column;gap:8px;"></div>
    </div>

    <div id="analytics_loader" style="text-align:center;padding:30px;color:#888;display:none;">⏳ Carregando analytics...</div>
  </div>


{% endif %}
</body>
</html>"""

@app.route("/gerar_link", methods=["POST"])
def gerar_link():
    if not session.get("logged_in"):
        return jsonify({"erro": "Não autorizado"}), 401

    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"link": url, "loja": "OUTRO"})

    loja = "OUTRO"
    if "aliexpress.com" in url:
        loja = "ALIEXPRESS"
        link = gerar_link_afiliado_aliexpress(url)
    elif "shopee.com.br" in url:
        loja = "SHOPEE"
        link = gerar_link_afiliado_shopee(url)
    elif "amazon.com.br" in url or "amzn.to" in url:
        loja = "AMAZON"
        link = url
        if AMAZON_TAG not in url:
            link = url + ("&" if "?" in url else "?") + f"tag={AMAZON_TAG}"
        link = encurtar_link(link)
    else:
        loja = "OUTRO"
        link = encurtar_link(url)

    return jsonify({"link": link, "loja": loja})


@app.route("/")
def index():
    return render_template_string(HTML, logged_in=session.get("logged_in", False), error=None, amazon_tag=AMAZON_TAG)

@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password", "") == WEB_PASSWORD:
        session["logged_in"] = True
        return redirect("/")
    return render_template_string(HTML, logged_in=False, error="Senha incorreta!", amazon_tag=AMAZON_TAG)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/publicar", methods=["POST"])
def publicar():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401

    data       = request.json
    nome       = data.get("nome", "").strip()
    preco      = float(data.get("preco", 0))
    preco_orig = float(data.get("preco_orig", 0))
    loja       = data.get("loja", "OUTRO")
    link       = data.get("link", "")
    imagem     = data.get("imagem", "")
    destaque   = data.get("destaque", "").strip()
    pub_tg        = data.get("telegram", True)
    pub_wa        = data.get("whatsapp", True)
    wa_principal  = data.get("wa_principal", True)
    wa_teste      = data.get("wa_teste", False)

    if not nome or not preco or not link:
        return jsonify({"ok": False, "erro": "Dados incompletos"})

    desc = int((1 - preco / preco_orig) * 100) if preco_orig > preco else 0

    # Inclui destaque no início do nome se preenchido
    nome_final = f"⭐ {destaque.upper()}\n{nome}" if destaque else nome

    produto = {
        "nome":           nome_final,
        "preco":          preco,
        "preco_original": preco_orig,
        "desconto":       desc,
        "loja":           loja,
        "frete":          "✅ Frete grátis" if loja in ("SHOPEE", "ALIEXPRESS") else "",
        "link_afiliado":  link,
        "imagem_url":     imagem,
        "score":          1,
        "fontes":         [],
    }

    try:
        imagem_path = gerar_imagem(produto)
        resultados = []

        if pub_tg:
            produto_tg = {**produto, "imagem_url": ""}
            ok_tg = postar_telegram(produto_tg, imagem_path)
            resultados.append("Telegram ✅" if ok_tg else "Telegram ❌")

        if pub_wa:
            grupos_postados = []
            if wa_principal:
                postar_whatsapp_grupo(produto, imagem_path, WHATSAPP_GROUP_ID)
                grupos_postados.append("Principal")
            if wa_teste:
                postar_whatsapp_grupo(produto, imagem_path, WHATSAPP_TEST_GROUP_ID)
                grupos_postados.append("Teste")
            if not wa_principal and not wa_teste:
                postar_whatsapp(produto, imagem_path)
                grupos_postados.append("Principal")
            resultados.append(f"WhatsApp ✅ ({', '.join(grupos_postados)})")

        # Registra no banco do bot como origem WEB
        try:
            BOT_API_URL = os.getenv("BOT_API_URL", "http://olhaisso.railway.internal:8081")
            WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")
            requests.post(
                BOT_API_URL + "/registrar",
                json={"nome": produto["nome"], "preco": produto["preco"],
                      "loja": produto["loja"], "origem": "WEB",
                      "link": produto.get("link_afiliado", "")},
                headers={"X-API-Key": WEB_SECRET_KEY},
                timeout=5
            )
        except Exception:
            pass
        msg = "Publicado em: " + " | ".join(resultados)
        return jsonify({"ok": True, "msg": msg})

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/encurtar_link", methods=["POST"])
def encurtar_link():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401
    data = request.json
    url_original = data.get("url", "").strip()
    if not url_original:
        return jsonify({"ok": False, "erro": "URL vazia"})
    try:
        r = requests.get(
            f"https://tinyurl.com/api-create.php?url={requests.utils.quote(url_original, safe='')}",
            timeout=10
        )
        if r.status_code == 200 and r.text.startswith("http"):
            return jsonify({"ok": True, "link": r.text.strip()})
        return jsonify({"ok": False, "erro": "TinyURL falhou", "link": url_original})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e), "link": url_original})


@app.route("/buscar_induzido", methods=["POST"])
def buscar_induzido():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401

    data       = request.json
    keyword    = data.get("keyword", "").strip()
    preco_min  = float(data.get("preco_min", 0) or 0)
    preco_max  = float(data.get("preco_max", 0) or 0)
    desc_min   = int(data.get("desconto_min", 0) or 0)
    qtde       = int(data.get("qtde", 3) or 3)
    usar_ml    = data.get("usar_ml", True)
    usar_shopee= data.get("usar_shopee", True)
    usar_ali   = data.get("usar_ali", True)
    usar_amazon= data.get("usar_amazon", True)
    pub_tg        = data.get("telegram", True)
    pub_wa        = data.get("whatsapp", True)
    wa_principal  = data.get("wa_principal", True)
    wa_teste      = data.get("wa_teste", False)

    if not keyword:
        return jsonify({"ok": False, "erro": "Palavra-chave obrigatória"})

    try:
        # Busca nas lojas selecionadas (ML removido — não funciona por keyword)
        produtos_raw = []
        if usar_shopee:
            r_shopee = busca_shopee_sem_filtro(keyword, limit=10)
            print(f"Busca induzida Shopee: {len(r_shopee)} produtos para '{keyword}'")
            produtos_raw += r_shopee
        if usar_ali:
            r_ali = busca_aliexpress_sem_filtro(keyword, limit=10)
            print(f"Busca induzida Ali: {len(r_ali)} produtos para '{keyword}'")
            produtos_raw += r_ali

        print(f"Busca induzida total bruto: {len(produtos_raw)} | filtros: R${preco_min}-{preco_max} desc>={desc_min}%")
        # Debug: mostra preço e desconto de cada produto bruto
        for p in produtos_raw[:5]:
            print(f"  -> {p['loja']} | R${p['preco']} | {p.get('desconto',0)}% | {p['nome'][:50]}")

        # Aplica filtros informados pelo usuário
        produtos = []
        for p in produtos_raw:
            if preco_min > 0 and p["preco"] < preco_min:
                continue
            if preco_max > 0 and p["preco"] > preco_max:
                continue
            if desc_min > 0 and p.get("desconto", 0) < desc_min:
                continue
            produtos.append(p)
        print(f"Busca induzida após filtro: {len(produtos)} produtos")

        # Ordena por maior desconto e limita pela qtde solicitada
        produtos.sort(key=lambda p: p.get("desconto", 0), reverse=True)
        produtos = produtos[:qtde]

        lojas_buscadas = []
        if usar_ml: lojas_buscadas.append("ML")
        if usar_shopee: lojas_buscadas.append("Shopee")
        if usar_ali: lojas_buscadas.append("AliExpress")
        if usar_amazon: lojas_buscadas.append("Amazon")

        if not produtos:
            return jsonify({"ok": False, "erro": f"Nenhum produto encontrado para '{keyword}' em {', '.join(lojas_buscadas)} com os filtros informados."})

        publicados = 0
        for produto in produtos:
            produto["nome"] = f"🏆 OFERTA PREMIUM DO CANAL\n{produto['nome']}"
            try:
                imagem_path = gerar_imagem(produto)
                if pub_tg:
                    produto_tg = {**produto, "imagem_url": ""}
                    postar_telegram(produto_tg, imagem_path)
                if pub_wa:
                    if wa_principal:
                        postar_whatsapp_grupo(produto, imagem_path, WHATSAPP_GROUP_ID)
                    if wa_teste:
                        postar_whatsapp_grupo(produto, imagem_path, WHATSAPP_TEST_GROUP_ID)
                    if not wa_principal and not wa_teste:
                        postar_whatsapp(produto, imagem_path)
                publicados += 1
                import time as _t
                _t.sleep(8)
            except Exception as e:
                print(f"Erro ao publicar: {e}")
                continue

        return jsonify({"ok": True, "msg": f"{publicados} Oferta(s) Premium publicadas para '{keyword}'"})

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/dados_produto_ml", methods=["POST"])
def dados_produto_ml():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Nao autorizado"}), 401

    data = request.json
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "erro": "URL obrigatoria"})

    # Normaliza URLs de oferta/deal do ML para URL de item individual (não /p/ de grupo)
    # Limpa a URL: remove fragment (#...) e parâmetros desnecessários
    # Mantém a URL de produto limpa para o ScrapingAnt
    import urllib.parse as _urlparse
    _parsed = _urlparse.urlparse(url)
    _qs = _urlparse.parse_qs(_parsed.query)
    _frag_str = _parsed.fragment  # ex: "origin=share&sid=share&wid=MLB4434632587&action=copy"
    _path = _parsed.path

    # Extrai wid= do fragment ou querystring (ID do item individual)
    _wid_m = re.search(r"wid=(MLB\d+)", _frag_str) or re.search(r"wid=(MLB\d+)", url)
    _wid = _wid_m.group(1) if _wid_m else None

    # Monta URL limpa — sempre mercadolivre.com.br sem fragment nem tracking
    if _wid:
        # Tem item individual — usa URL de produto direto
        url = f"https://www.mercadolivre.com.br/p/{_wid}"
    elif "/p/" in _path:
        # Página de grupo sem wid — limpa só o fragment/tracking
        m_p = re.search(r"/p/(MLB\d+)", _path)
        if m_p:
            url = f"https://www.mercadolivre.com.br/p/{m_p.group(1)}"
    else:
        # URL normal de produto — remove só o fragment
        url = _urlparse.urlunparse(_parsed._replace(fragment="", query=""))

    SCRAPINGANT_KEY = os.getenv("SCRAPINGANT_KEY", "")
    SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY", "")

    try:
        # ── Estratégia 1: API pública do ML (sem scraping, mais confiável) ──
        m_id = re.search(r"MLB[\-]?(\d+)", url)
        if m_id:
            item_id = f"MLB{m_id.group(1)}"
            api_r = requests.get(
                f"https://api.mercadolibre.com/items/{item_id}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15
            )
            if api_r.status_code == 200:
                d = api_r.json()
                nome      = d.get("title", "")
                preco     = float(d.get("price") or 0)
                preco_orig = float(d.get("original_price") or 0)
                pics      = d.get("pictures", [])
                imagem    = pics[0].get("secure_url", "") if pics else d.get("thumbnail", "")
                # Imagem HD: troca -I.jpg por -F.jpg
                imagem = re.sub(r"-[A-Z]\.(jpg|jpeg|webp)$", "-F.jpg", imagem)
                if nome and preco:
                    return jsonify({
                        "ok":         True,
                        "nome":       nome,
                        "preco":      round(preco, 2),
                        "preco_orig": round(preco_orig, 2) if preco_orig > preco else None,
                        "imagem":     imagem,
                    })

        # ── Estratégia 2: ScrapingAnt (fallback para URLs sem ID claro) ──
        needs_js = "/p/MLB" in url
        if SCRAPINGANT_KEY:
            params = {
                "url":           url,
                "x-api-key":     SCRAPINGANT_KEY,
                "proxy_country": "BR",
                "browser":       "true" if needs_js else "false",
            }
            r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=60)
            # Se browser=false retornou "requires JavaScript", tenta com browser=true
            if r.status_code == 200 and "requires JavaScript" in r.text:
                params["browser"] = "true"
                r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=60)
        else:
            payload = {
                "api_key":      SCRAPERAPI_KEY,
                "url":          url,
                "country_code": "br",
                "render":       "true" if needs_js else "false",
            }
            r = requests.get("https://api.scraperapi.com", params=payload, timeout=60)

        if r.status_code != 200:
            return jsonify({"ok": False, "erro": "Erro ao acessar pagina do produto"})

        html = r.text

        def _extrair_nome(html):
            # Página /p/ (grupo de produto) — JSON interno
            for pat in [
                r'"title"\s*:\s*"([^"]{10,300})"',
                r'"product_title"\s*:\s*"([^"]{10,300})"',
                r'"name"\s*:\s*"([^"]{10,300})"',
                r'<h1[^>]*class="[^"]*ui-pdp-title[^"]*"[^>]*>\s*([^<]{10,300})\s*</h1>',
                r'<h1[^>]*>\s*([^<]{10,300})\s*</h1>',
                r'"og:title"\s+content="([^"]{10,300})"',
                r'<title>([^<]{10,200})\s*[\|\-]',
            ]:
                m = re.search(pat, html)
                if m:
                    nome = m.group(1).strip()
                    # Filtrar títulos genéricos/inúteis
                    if any(x in nome.lower() for x in ['mercado livre', 'meli', '{', 'undefined']):
                        continue
                    return nome
            return ""

        def _extrair_preco(html):
            # Tenta JSON estruturado primeiro (mais confiável)
            for pat in [
                r'"price"\s*:\s*([\d]+\.?\d*)',
                r'"selling_price"\s*:\s*([\d]+\.?\d*)',
                r'"amount"\s*:\s*([\d]+\.?\d*)',
            ]:
                m = re.search(pat, html)
                if m:
                    v = float(m.group(1))
                    if 10 < v < 100000:
                        return v
            # Fallback HTML
            m = re.search(r'class="andes-money-amount__fraction"[^>]*>(\d[\d\.]*)<', html)
            if m:
                try:
                    v = float(m.group(1).replace(".", ""))
                    if 10 < v < 100000:
                        return v
                except:
                    pass
            return 0.0

        def _extrair_preco_orig(html):
            for pat in [
                r'"original_price"\s*:\s*([\d]+\.?\d*)',
                r'"base_price"\s*:\s*([\d]+\.?\d*)',
            ]:
                m = re.search(pat, html)
                if m:
                    v = float(m.group(1))
                    if v > 0:
                        return v
            return 0.0

        nome      = _extrair_nome(html)
        preco     = _extrair_preco(html)
        preco_orig = _extrair_preco_orig(html)

        # Extrai imagem principal HD
        imagem = ''
        PAT_2X = re.compile(r'https://http2\.mlstatic\.com/D_NQ_NP_2X_\S+')
        PAT_F  = re.compile(r'https://http2\.mlstatic\.com/\S+-F\.(webp|jpg|jpeg)')
        PAT_ANY= re.compile(r'https://http2\.mlstatic\.com/D_\S+\.(webp|jpg|jpeg)')
        m2x = PAT_2X.search(html)
        if m2x:
            imagem = m2x.group(0).split('"')[0].split("'")[0]
        if not imagem:
            mf = PAT_F.search(html)
            if mf:
                imagem = mf.group(0).split('"')[0].split("'")[0]
        if not imagem:
            many = PAT_ANY.search(html)
            if many:
                url = many.group(0).split('"')[0].split("'")[0]
                url = url.replace('D_Q_NP_', 'D_NQ_NP_2X_')
                if '2X' not in url:
                    url = url.replace('D_NQ_NP_', 'D_NQ_NP_2X_')
                url = re.sub(r'-[A-Z]\.(webp|jpg|jpeg)$', '-F.webp', url)
                imagem = url
        if not imagem:
            mi = re.search(r'<img[^>]+class="[^"]*ui-pdp-image[^"]*"[^>]+src="([^"]+)"', html)
            if mi:
                imagem = mi.group(1)

        if not nome and not preco:
            return jsonify({"ok": False, "erro": "Nao foi possivel extrair dados do produto. Tente preencher manualmente."})

        return jsonify({
            "ok":        True,
            "nome":      nome,
            "preco":     round(preco, 2) if preco else None,
            "preco_orig": round(preco_orig, 2) if preco_orig > preco else None,
            "imagem":    imagem,
        })

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/limpar_historico", methods=["POST"])
def limpar_historico():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Nao autorizado"}), 401
    try:
        BOT_API_URL = os.getenv("BOT_API_URL", "http://olhaisso.railway.internal:8081")
        WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")
        r = requests.post(
            BOT_API_URL + "/limpar_historico",
            headers={"X-API-Key": WEB_SECRET_KEY},
            timeout=15
        )
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify({"ok": False, "erro": f"Bot retornou {r.status_code}"})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/disparar_ciclo", methods=["POST"])
def disparar_ciclo():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Nao autorizado"}), 401
    try:
        data = request.json
        BOT_API_URL = os.getenv("BOT_API_URL", "http://olhaisso.railway.internal:8081")
        WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")
        r = requests.post(
            BOT_API_URL + "/ciclo",
            json=data,
            headers={"X-API-Key": WEB_SECRET_KEY},
            timeout=180
        )
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify({"ok": False, "erro": f"Bot retornou {r.status_code}"})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/disparar_ciclo_tb", methods=["POST"])
def disparar_ciclo_tb():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Nao autorizado"}), 401
    try:
        BOT_API_URL = os.getenv("BOT_API_URL", "http://olhaisso.railway.internal:8081")
        WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")
        data = request.json or {}
        r = requests.post(
            BOT_API_URL + "/ciclo_tb",
            json={
                "telegram":     data.get("telegram", True),
                "wa_principal": data.get("wa_principal", True),
                "wa_teste":     data.get("wa_teste", False),
                "qtde":         data.get("qtde", 4),
            },
            headers={"X-API-Key": WEB_SECRET_KEY},
            timeout=180
        )
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify({"ok": False, "erro": "Bot retornou " + str(r.status_code)})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/historico_proxy")
def historico_proxy():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Nao autorizado"}), 401
    try:
        loja = request.args.get("loja", "").strip()
        BOT_API_URL = os.getenv("BOT_API_URL", "http://olhaisso.railway.internal:8081")
        WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")
        params = {}
        if loja:
            params["loja"] = loja
        r = requests.get(
            BOT_API_URL + "/historico",
            headers={"X-API-Key": WEB_SECRET_KEY},
            params=params,
            timeout=30
        )
        if r.status_code == 200:
            rows = r.json()
            if loja:
                rows = [x for x in rows if x.get("loja") == loja]
            return jsonify({"ok": True, "rows": rows})
        return jsonify({"ok": False, "erro": "Bot API retornou " + str(r.status_code)})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/dados_produto_amazon", methods=["POST"])
def dados_produto_amazon():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Nao autorizado"}), 401

    data = request.json
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "erro": "URL obrigatoria"})

    SCRAPINGANT_KEY = os.getenv("SCRAPINGANT_KEY", "")
    if not SCRAPINGANT_KEY:
        return jsonify({"ok": False, "erro": "SCRAPINGANT_KEY nao configurada no Railway"})

    try:
        params = {
            "url":           url,
            "x-api-key":     SCRAPINGANT_KEY,
            "proxy_country": "BR",
            "browser":       "false",
        }
        r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=30)
        if r.status_code != 200:
            return jsonify({"ok": False, "erro": "Erro ao acessar pagina do produto Amazon"})

        html = r.text

        # Extrai nome
        nome = ""
        for pat in [
            r'"product_title"\s*:\s*"([^"]{10,300})"',
            r'id="productTitle"[^>]*>\s*([^<]{10,300})',
            r'"name"\s*:\s*"([^"]{10,300})"',
        ]:
            m = re.search(pat, html)
            if m:
                nome = m.group(1).strip()
                break

        # Extrai preço
        preco = 0.0
        for pat in [
            r'"price"\s*:\s*"R\$\s*([\d,\.]+)"',
            r'class="a-price-whole"[^>]*>([\d\.]+)',
            r'"priceAmount"\s*:\s*([\d\.]+)',
        ]:
            m = re.search(pat, html)
            if m:
                try:
                    preco = float(m.group(1).replace(".", "").replace(",", "."))
                    if preco > 0:
                        break
                except:
                    pass

        # Extrai imagem
        imagem = ""
        for pat in [
            r'"hiRes"\s*:\s*"(https://[^"]+\.jpg)"',
            r'"large"\s*:\s*"(https://[^"]+\.jpg)"',
            r'data-old-hires="(https://[^"]+\.jpg)"',
            r'"mainUrl"\s*:\s*"(https://[^"]+\.jpg)"',
            r'id="landingImage"[^>]+src="(https://[^"]+)"',
        ]:
            m = re.search(pat, html)
            if m:
                imagem = m.group(1)
                break

        if not nome:
            return jsonify({"ok": False, "erro": "Nao foi possivel extrair dados. Preencha manualmente."})

        return jsonify({
            "ok":        True,
            "nome":      nome,
            "preco":     round(preco, 2) if preco else None,
            "preco_orig": None,
            "imagem":    imagem,
        })
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/gerar_link_ml", methods=["POST"])
def gerar_link_ml():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401

    data = request.json
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "erro": "URL obrigatória"})

    try:
        from mercadolivre_link import gerar_link_afiliado_ml
        link = gerar_link_afiliado_ml(url)
        if link:
            return jsonify({"ok": True, "link": link})
        return jsonify({"ok": False, "erro": "Não foi possível gerar o link. Verifique se ML_COOKIES_JSON está configurado no Railway."})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/buscar_internet", methods=["POST"])
def buscar_internet():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401

    data      = request.json
    keyword   = data.get("keyword", "").strip()
    preco_min = float(data.get("preco_min", 0) or 0)
    preco_max = float(data.get("preco_max", 0) or 0)

    if not keyword:
        return jsonify({"ok": False, "erro": "Palavra-chave obrigatória"})

    SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
    if not SERPAPI_KEY:
        return jsonify({"ok": False, "erro": "SERPAPI_KEY não configurada no Railway"})

    try:
        params = {
            "engine":  "google_shopping",
            "q":       keyword,
            "gl":      "br",
            "hl":      "pt",
            "num":     20,
            "api_key": SERPAPI_KEY,
        }

        r = requests.get("https://serpapi.com/search", params=params, timeout=20)

        if r.status_code != 200:
            return jsonify({"ok": False, "erro": f"Erro SerpApi: {r.status_code} — {r.text[:200]}"})

        items = r.json().get("shopping_results", [])

        if not items:
            return jsonify({"ok": False, "erro": f"Nenhum resultado encontrado para '{keyword}'"})

        resultados = []
        for item in items:
            nome   = item.get("title", "").strip()
            link   = item.get("link") or item.get("product_link", "")
            loja   = item.get("source", "")
            imagem = item.get("thumbnail", "")

            # Preço atual
            preco_raw = item.get("price", "")
            preco_num = 0.0
            preco_str = ""
            if preco_raw:
                preco_str = str(preco_raw).strip()
                try:
                    preco_num = float(re.sub(r'[^\d,]', '', preco_str).replace(',', '.'))
                except:
                    pass

            # Preço original (antes do desconto)
            preco_orig_str = ""
            preco_orig_num = 0.0
            desconto_pct   = 0

            # Tenta pegar preço original de vários campos possíveis
            for campo in ["extracted_price", "old_price", "was_price"]:
                val = item.get(campo)
                if val:
                    try:
                        preco_orig_num = float(str(val).replace(",", "."))
                        break
                    except:
                        pass

            # Se não encontrou via campo direto, tenta via "price_details"
            if preco_orig_num == 0:
                price_details = item.get("price_details", "")
                if price_details:
                    match = re.search(r'R\$\s*([\d\.,]+)', str(price_details))
                    if match:
                        try:
                            preco_orig_num = float(match.group(1).replace('.', '').replace(',', '.'))
                        except:
                            pass

            if preco_orig_num > 0 and preco_orig_num > preco_num:
                preco_orig_str = f"R$ {preco_orig_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                desconto_pct = int((1 - preco_num / preco_orig_num) * 100)

            if not nome or not link:
                continue

            # Filtro preço mínimo
            if preco_min > 0 and preco_num > 0 and preco_num < preco_min:
                continue

            # Filtro preço máximo
            if preco_max > 0 and preco_num > 0 and preco_num > preco_max:
                continue

            resultados.append({
                "nome":        nome,
                "preco":       preco_str,
                "preco_orig":  preco_orig_str,
                "desconto":    desconto_pct,
                "loja":        loja,
                "link":        link,
                "imagem":      imagem,
            })

            if len(resultados) >= 10:
                break

        if not resultados:
            return jsonify({"ok": False, "erro": f"Nenhum resultado encontrado para '{keyword}'" + (f" com preço até R${preco_max:.0f}" if preco_max > 0 else "")})

        return jsonify({"ok": True, "resultados": resultados})

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
