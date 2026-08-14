"""
scraper.py — Buscador stealth de ofertas
=========================================
Roda 3x por dia com nichos diferentes para cada período:
  - Manhã   → Suplementos e fitness (público que malha cedo ou planeja)
  - Tarde   → Pet e casa (pesquisa durante almoço)
  - Noite   → Moda, tênis e eletrônicos (maior poder de compra pós-trabalho)

Usa Playwright com todas as técnicas de stealth do utils.py para
não ser detectado como bot pelo Mercado Livre.
"""

import json
import random
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from utils import (
    configurar_contexto_stealth, aplicar_stealth,
    espera_humana, scroll_humano, periodo_atual
)

# ── Nichos por período ────────────────────────────────────────────────────────
NICHOS = {
    "manha": [
        {"q": "whey protein 1kg",         "min_off": 20},
        {"q": "creatina monohidratada",    "min_off": 20},
        {"q": "pre treino termogenico",    "min_off": 15},
        {"q": "shaker coqueteleira",       "min_off": 25},
        {"q": "roupa academia feminina",   "min_off": 30},
    ],
    "tarde": [
        {"q": "racao golden cachorro",     "min_off": 20},
        {"q": "coleira antipulgas",        "min_off": 20},
        {"q": "arranhador gato",           "min_off": 25},
        {"q": "comedouro automatico pet",  "min_off": 20},
        {"q": "brinquedo interativo gato", "min_off": 20},
    ],
    "noite": [
        {"q": "tenis corrida masculino",   "min_off": 25},
        {"q": "camiseta dry fit",          "min_off": 30},
        {"q": "fone bluetooth",            "min_off": 25},
        {"q": "smartwatch",                "min_off": 20},
        {"q": "mochila esportiva",         "min_off": 25},
    ],
}

MAX_FINAL      = 8    # max de ofertas que vamos postar por rodada
MAX_POR_TERMO  = 15   # max de cards verificados por busca


def extrair_numero(texto):
    if not texto:
        return None
    limpo = "".join(c for c in texto if c.isdigit() or c == ",")
    try:
        return float(limpo.replace(",", "."))
    except Exception:
        return None


def extrair_oferta(card):
    """Extrai dados de um card de produto. Retorna None se não for válido."""
    try:
        # Título
        titulo_el = card.query_selector(
            ".ui-search-item__title, .poly-component__title"
        )
        if not titulo_el:
            return None
        titulo = titulo_el.inner_text().strip()
        if not titulo:
            return None

        # Badge de desconto (ex: "32% OFF")
        badge_el = card.query_selector(
            ".andes-badge--discount, [class*='discount'], .ui-search-price__discount"
        )
        desconto = 0
        if badge_el:
            badge_txt = badge_el.inner_text().upper()
            numeros   = "".join(c for c in badge_txt if c.isdigit())
            desconto  = int(numeros) if numeros else 0

        # Preço atual
        preco_el = card.query_selector(
            ".ui-search-price__part:not(.ui-search-price__original-value) "
            ".andes-money-amount__fraction"
        )
        preco_atual = extrair_numero(preco_el.inner_text() if preco_el else None)
        if not preco_atual:
            return None

        # Preço original (riscado) — pode não existir
        orig_el      = card.query_selector(
            ".ui-search-price__original-value .andes-money-amount__fraction"
        )
        preco_orig   = extrair_numero(orig_el.inner_text() if orig_el else None)
        if not preco_orig or preco_orig <= preco_atual:
            preco_orig = preco_atual

        # Se não tinha badge mas tem preços diferentes, calcula desconto
        if desconto == 0 and preco_orig > preco_atual:
            desconto = round((1 - preco_atual / preco_orig) * 100)

        # URL do produto
        link_el = card.query_selector(
            "a.ui-search-link, a.poly-component__title, "
            "a[class*='result-link'], a[href*='produto.mercadolivre']"
        )
        if not link_el:
            return None
        url = link_el.get_attribute("href", timeout=3000) or ""
        url = url.split("#")[0].split("?")[0]
        if not url or "mercadolivre" not in url:
            return None

        # Imagem
        img_el = card.query_selector(
            "img.ui-search-result-image__element, "
            "img.poly-component__picture, img[src*='mlstatic']"
        )
        imagem = ""
        if img_el:
            imagem = (img_el.get_attribute("src") or
                      img_el.get_attribute("data-src") or "")
        imagem = imagem.replace("http://", "https://")

        return {
            "titulo":         titulo,
            "preco_original": preco_orig,
            "preco_atual":    preco_atual,
            "desconto":       desconto,
            "url":            url,
            "imagem":         imagem,
            "link_afiliado":  "",
        }
    except Exception:
        return None


def scrape_termo(page, termo, min_off):
    url = (
        f"https://lista.mercadolivre.com.br/"
        f"{termo.replace(' ', '-')}"
        f"_PriceDiscount_10-100"
    )
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        espera_humana(2, 5)
        scroll_humano(page, vezes=random.randint(2, 4))
        espera_humana(1, 3)
    except PWTimeout:
        print(f"  [timeout] '{termo}'")
        return []

    cards = page.query_selector_all(".ui-search-result__wrapper")[:MAX_POR_TERMO]
    encontrados = []
    for card in cards:
        oferta = extrair_oferta(card)
        if oferta and oferta["desconto"] >= min_off and oferta["imagem"]:
            encontrados.append(oferta)
    return encontrados


def main():
    periodo = periodo_atual()
    buscas  = NICHOS[periodo]
    print(f"Período: {periodo.upper()} | {len(buscas)} nichos para buscar\n")

    vistos  = set()
    ofertas = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        ctx  = browser.new_context(**configurar_contexto_stealth())
        page = ctx.new_page()
        aplicar_stealth(page)

        # Visita a homepage primeiro (comportamento mais humano)
        try:
            page.goto("https://www.mercadolivre.com.br", wait_until="domcontentloaded", timeout=30000)
            espera_humana(2, 4)
        except Exception:
            pass

        for busca in buscas:
            print(f"  Buscando: '{busca['q']}' (≥{busca['min_off']}% OFF)...")
            try:
                encontrados = scrape_termo(page, busca["q"], busca["min_off"])
                novos = 0
                for o in encontrados:
                    if o["url"] not in vistos:
                        vistos.add(o["url"])
                        ofertas.append(o)
                        novos += 1
                print(f"    → {novos} nova(s) oferta(s)")
            except Exception as e:
                print(f"    → erro: {e}")

            espera_humana(4, 9)   # pausa entre buscas (humano leva tempo)

        browser.close()

    ofertas.sort(key=lambda o: o["desconto"], reverse=True)
    selecionadas = ofertas[:MAX_FINAL]

    with open("ofertas.json", "w", encoding="utf-8") as f:
        json.dump(selecionadas, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(selecionadas)} oferta(s) prontas:")
    for o in selecionadas:
        print(f"   {o['desconto']:3d}% OFF | R$ {o['preco_atual']:.2f} | {o['titulo'][:50]}")


if __name__ == "__main__":
    main()
