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
)

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
        <input type="checkbox" id="af_whatsapp" checked onchange="toggleDestino('dest_wa_af', this)">
        <span>📱 WhatsApp</span>
      </label>
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
        <input type="checkbox" id="pr_whatsapp" checked onchange="toggleDestino('dest_wa_pr', this)">
        <span>📱 WhatsApp</span>
      </label>
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

    <label>🏷️ Desconto mínimo (%) *</label>
    <input type="number" id="bk_desconto_min" step="1" min="0" max="99" placeholder="Ex: 20 (use 0 para sem limite)">

    <label style="margin-bottom:8px;">📢 Publicar em:</label>
    <div class="destinos">
      <label class="destino on" id="dest_tg_bk">
        <input type="checkbox" id="bk_telegram" checked onchange="toggleDestino('dest_tg_bk', this)">
        <span>✈️ Telegram</span>
      </label>
      <label class="destino on" id="dest_wa_bk">
        <input type="checkbox" id="bk_whatsapp" checked onchange="toggleDestino('dest_wa_bk', this)">
        <span>📱 WhatsApp</span>
      </label>
    </div>

    <button class="btn btn-orange" id="btn_bk" onclick="buscarInduzido()">🔍 Buscar e publicar Oferta Premium</button>
    <div class="loader" id="loader_bk">⏳ Buscando ofertas...</div>
  </div>

  <!-- FLUXO 4: Busca na Internet -->
  <div class="card" id="card_web">
    <h2>🌐 Busca de Ofertas na Internet</h2>
    <div class="info">💡 Busca em Amazon, Mercado Livre e outros — traz links crus para você trabalhar manualmente</div>

    <label>🔑 O que você está procurando? *</label>
    <input type="text" id="wb_keyword" placeholder="Ex: notebook Dell, iPhone 15, monitor Samsung...">

    <div class="row2">
      <div>
        <label>💰 Preço máximo (R$)</label>
        <input type="number" id="wb_preco_max" step="0.01" placeholder="Ex: 2000 (opcional)">
      </div>
      <div>
        <label>🏷️ Desconto mínimo (%)</label>
        <input type="number" id="wb_desconto_min" step="1" min="0" max="99" placeholder="Ex: 10 (opcional)">
      </div>
    </div>

    <button class="btn btn-blue" id="btn_wb" onclick="buscarInternet()" style="background:#0088cc;">🌐 Buscar ofertas agora</button>
    <div class="loader" id="loader_wb">⏳ Pesquisando na internet...</div>

    <div id="wb_resultados" style="margin-top:16px;"></div>
  </div>
</div>

<script>
function trocarAba(aba) {
  const abas = ['afiliado', 'produto', 'busca', 'web'];
  document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', aba === abas[i]));
  abas.forEach(a => {
    const card = document.getElementById('card_' + a);
    if (card) card.classList.toggle('active', aba === a);
  });
}

function toggleDestino(id, checkbox) {
  document.getElementById(id).classList.toggle('on', checkbox.checked);
}

function abrirLink(inputId) {
  const url = document.getElementById(inputId).value.trim();
  if (!url) return alert('Cole o link primeiro!');
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

  if (!link)   return alert('Cole o link de afiliado!');
  if (!nome)   return alert('Preencha o nome do produto!');
  if (!preco)  return alert('Preencha o preço atual!');
  if (!imagem) return alert('Cole a URL da imagem!');
  if (!telegram && !whatsapp) return alert('Selecione ao menos um destino!');

  await enviar(
    { nome, preco, preco_orig, loja, link, imagem, destaque, telegram, whatsapp },
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

  if (!link)   return alert('Cole o link do produto!');
  if (!preco)  return alert('Preencha o preço atual!');
  if (!imagem) return alert('Cole a URL da imagem!');
  if (!telegram && !whatsapp) return alert('Selecione ao menos um destino!');

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
      { nome, preco, preco_orig, loja, link: linkFinal, imagem, destaque, telegram, whatsapp },
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
  const telegram     = document.getElementById('bk_telegram').checked;
  const whatsapp     = document.getElementById('bk_whatsapp').checked;

  if (!keyword)  return alert('Digite uma palavra-chave!');
  if (!preco_min) return alert('Informe o preço mínimo!');
  if (!preco_max) return alert('Informe o preço máximo!');
  if (preco_max <= preco_min) return alert('Preço máximo deve ser maior que o mínimo!');
  if (desconto_min === '') return alert('Informe o desconto mínimo (use 0 para sem limite)!');
  if (!telegram && !whatsapp) return alert('Selecione ao menos um destino!');

  // Monta keyword final — marca é opcional
  const keyword_final = marca ? `${keyword} ${marca}` : keyword;

  const btn = document.getElementById('btn_bk');
  btn.disabled = true;
  document.getElementById('loader_bk').style.display = 'block';
  document.getElementById('loader_bk').textContent = '⏳ Buscando ofertas em Shopee + AliExpress...';

  try {
    const resp = await fetch('/buscar_induzido', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ keyword: keyword_final, preco_min, preco_max, desconto_min: parseInt(desconto_min), telegram, whatsapp })
    });
    const data = await resp.json();
    if (data.ok) {
      mostrarMsg(`<div class="msg msg-ok">✅ ${data.msg}</div>`);
      document.getElementById('bk_keyword').value = '';
      document.getElementById('bk_marca').value = '';
      document.getElementById('bk_preco_min').value = '';
      document.getElementById('bk_preco_max').value = '';
      document.getElementById('bk_desconto_min').value = '';
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

async function buscarInternet() {
  const keyword     = document.getElementById('wb_keyword').value.trim();
  const preco_max   = parseFloat(document.getElementById('wb_preco_max').value) || 0;
  const desc_min    = parseInt(document.getElementById('wb_desconto_min').value) || 0;

  if (!keyword) return alert('Digite o que está procurando!');

  const btn = document.getElementById('btn_wb');
  btn.disabled = true;
  document.getElementById('loader_wb').style.display = 'block';
  document.getElementById('wb_resultados').innerHTML = '';

  try {
    const resp = await fetch('/buscar_internet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ keyword, preco_max, desc_min })
    });
    const data = await resp.json();
    const area = document.getElementById('wb_resultados');

    if (data.ok && data.resultados && data.resultados.length > 0) {
      let html = `<div style="color:#aaa;font-size:13px;margin-bottom:12px;">✅ ${data.resultados.length} ofertas encontradas — clique em "Copiar Link" para usar nas outras abas</div>`;
      data.resultados.forEach((r, i) => {
        html += `
        <div style="background:#222;border-radius:12px;padding:14px;margin-bottom:12px;border:1px solid #333;">
          <div style="font-size:14px;font-weight:700;color:#fff;margin-bottom:6px;">${r.nome}</div>
          <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px;">
            ${r.preco ? `<span style="color:#FF6B1A;font-weight:700;font-size:15px;">${r.preco}</span>` : ''}
            ${r.desconto ? `<span style="background:#00BB44;color:#fff;padding:2px 8px;border-radius:6px;font-size:13px;">${r.desconto}</span>` : ''}
            ${r.loja ? `<span style="color:#aaa;font-size:13px;">🏪 ${r.loja}</span>` : ''}
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <input type="text" value="${r.link}" readonly style="flex:1;font-size:12px;padding:8px;background:#1a1a1a;border:1px solid #444;border-radius:8px;color:#88cc88;">
            <button onclick="navigator.clipboard.writeText('${r.link}').then(()=>this.textContent='✅ Copiado!').catch(()=>this.textContent='Erro')"
              style="background:#0088cc;color:#fff;border:none;border-radius:8px;padding:8px 14px;cursor:pointer;font-size:13px;white-space:nowrap;">
              📋 Copiar Link
            </button>
          </div>
        </div>`;
      });
      area.innerHTML = html;
    } else {
      area.innerHTML = `<div class="msg msg-err">❌ ${data.erro || 'Nenhuma oferta encontrada'}</div>`;
    }
  } catch(e) {
    document.getElementById('wb_resultados').innerHTML = `<div class="msg msg-err">❌ Erro: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    document.getElementById('loader_wb').style.display = 'none';
  }
}
</script>
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
    pub_tg     = data.get("telegram", True)
    pub_wa     = data.get("whatsapp", True)

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
            postar_whatsapp(produto, imagem_path)
            resultados.append("WhatsApp ✅")

        msg = "Publicado em: " + " | ".join(resultados)
        return jsonify({"ok": True, "msg": msg})

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/buscar_induzido", methods=["POST"])
def buscar_induzido():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401

    data       = request.json
    keyword    = data.get("keyword", "").strip()
    preco_min  = float(data.get("preco_min", 0) or 0)
    preco_max  = float(data.get("preco_max", 0) or 0)
    desc_min   = int(data.get("desconto_min", 0) or 0)
    pub_tg     = data.get("telegram", True)
    pub_wa     = data.get("whatsapp", True)

    if not keyword:
        return jsonify({"ok": False, "erro": "Palavra-chave obrigatória"})

    try:
        # Usa funções próprias SEM filtros do Railway
        produtos_raw = []
        produtos_raw += busca_shopee_sem_filtro(keyword, limit=10)
        produtos_raw += busca_aliexpress_sem_filtro(keyword, limit=10)

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

        # Ordena por maior desconto
        produtos.sort(key=lambda p: p.get("desconto", 0), reverse=True)
        produtos = produtos[:6]

        if not produtos:
            return jsonify({"ok": False, "erro": f"Nenhum produto encontrado para '{keyword}' com os filtros informados. Tente reduzir o preço mínimo, aumentar o preço máximo ou diminuir o desconto mínimo. Shopee e AliExpress raramente têm produtos acima de R$1.500."})

        publicados = 0
        for produto in produtos:
            produto["nome"] = f"🏆 OFERTA PREMIUM DO CANAL\n{produto['nome']}"
            try:
                imagem_path = gerar_imagem(produto)
                if pub_tg:
                    produto_tg = {**produto, "imagem_url": ""}
                    postar_telegram(produto_tg, imagem_path)
                if pub_wa:
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


@app.route("/buscar_internet", methods=["POST"])
def buscar_internet():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401

    data      = request.json
    keyword   = data.get("keyword", "").strip()
    preco_max = float(data.get("preco_max", 0) or 0)
    desc_min  = int(data.get("desc_min", 0) or 0)

    if not keyword:
        return jsonify({"ok": False, "erro": "Palavra-chave obrigatória"})

    try:
        # Monta prompt para o Claude buscar ofertas na internet
        filtros = []
        if preco_max > 0:
            filtros.append(f"preço máximo R${preco_max:.0f}")
        if desc_min > 0:
            filtros.append(f"desconto mínimo {desc_min}%")
        filtros_txt = f" com {', '.join(filtros)}" if filtros else ""

        prompt = f"""Pesquise na internet as melhores ofertas atuais de "{keyword}"{filtros_txt} nos principais marketplaces brasileiros (Amazon, Mercado Livre, Magalu, Americanas, Casas Bahia, Shopee, AliExpress).

Retorne APENAS um JSON válido, sem texto extra, sem markdown, sem explicações. Formato exato:
{{
  "resultados": [
    {{
      "nome": "Nome completo do produto",
      "preco": "R$ 1.299,00",
      "desconto": "35% OFF",
      "loja": "Amazon",
      "link": "https://..."
    }}
  ]
}}

Traga até 6 ofertas reais com links funcionais. Se não encontrar, retorne {{"resultados": []}}."""

        ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        if not ANTHROPIC_KEY:
            return jsonify({"ok": False, "erro": "ANTHROPIC_API_KEY não configurada no Railway"})

        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )

        if r.status_code != 200:
            return jsonify({"ok": False, "erro": f"Erro na API: {r.status_code}"})

        resp_data = r.json()

        # Extrai texto da resposta
        texto = ""
        for block in resp_data.get("content", []):
            if block.get("type") == "text":
                texto += block.get("text", "")

        # Parse do JSON retornado
        import re as _re
        json_match = _re.search(r'\{.*\}', texto, _re.DOTALL)
        if not json_match:
            return jsonify({"ok": False, "erro": "Não foi possível obter resultados da busca"})

        resultado = json.loads(json_match.group())
        resultados = resultado.get("resultados", [])

        if not resultados:
            return jsonify({"ok": False, "erro": f"Nenhuma oferta encontrada para '{keyword}'"})

        return jsonify({"ok": True, "resultados": resultados})

    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
