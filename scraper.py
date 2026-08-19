"""
scraper.py — Buscador TURBINADO com 20+ nichos, logging, desconto 15%
"""
import json
import random
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from utils import (
    configurar_contexto_stealth, aplicar_stealth,
    espera_humana, scroll_humano, periodo_atual, carregar_historico
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

NICHOS = {
    "manha": [
        {"q": "whey protein",             "min_off": 15},
        {"q": "whey isolado",             "min_off": 15},
        {"q": "creatina",                 "min_off": 15},
        {"q": "bcaa",                     "min_off": 15},
        {"q": "pre treino",               "min_off": 12},
        {"q": "termogenico",              "min_off": 15},
        {"q": "roupa academia feminina",  "min_off": 18},
        {"q": "roupa academia masculina", "min_off": 18},
        {"q": "short fitness",            "min_off": 18},
        {"q": "top fitness",              "min_off": 18},
        {"q": "shaker",                   "min_off": 18},
        {"q": "fone bluetooth fitness",   "min_off": 18},
        {"q": "garrafa agua",             "min_off": 15},
        {"q": "suplemento",               "min_off": 15},
        {"q": "fitness",                  "min_off": 15},
    ],
    "tarde": [
        {"q": "racao cachorro",           "min_off": 15},
        {"q": "racao gato",               "min_off": 15},
        {"q": "racao premium",            "min_off": 15},
        {"q": "coleira cachorro",         "min_off": 15},
        {"q": "arreio cachorro",          "min_off": 15},
        {"q": "cama pet",                 "min_off": 15},
        {"q": "brinquedo pet",            "min_off": 15},
        {"q": "shampoo pet",              "min_off": 15},
        {"q": "antipulgas",               "min_off": 15},
        {"q": "vitamina pet",             "min_off": 15},
        {"q": "pet shop",                 "min_off": 12},
        {"q": "cachorro",                 "min_off": 12},
        {"q": "gato",                     "min_off": 12},
    ],
    "noite": [
        {"q": "tenis",                    "min_off": 15},
        {"q": "tenis esportivo",          "min_off": 15},
        {"q": "camiseta",                 "min_off": 18},
        {"q": "bermuda",                  "min_off": 18},
        {"q": "jaqueta",                  "min_off": 15},
        {"q": "roupas",                   "min_off": 18},
        {"q": "fone",                     "min_off": 15},
        {"q": "smartwatch",               "min_off": 15},
        {"q": "mochila",                  "min_off": 18},
        {"q": "relogio",                  "min_off": 15},
        {"q": "garrafa termica",          "min_off": 18},
        {"q": "moda",                     "min_off": 15},
    ],
}

MAX_FINAL = 10
MAX_POR_TERMO = 20


def extrair_numero(texto):
    if not texto:
        return None
    limpo = "".join(c for c in texto if c.isdigit() or c == ",")
    try:
        return float(limpo.replace(",", "."))
    except Exception:
        return None


def extrair_oferta(card):
    try:
        titulo_el = card.query_selector(".ui-search-item__title, .poly-component__title")
        if not titulo_el:
            return None
        titulo = titulo_el.inner_text().strip()
        if not titulo or len(titulo) < 10:
            return None

        badge_el = card.query_selector(".andes-badge--discount, [class*='discount'], .ui-search-price__discount")
        desconto = 0
        if badge_el:
            numeros = "".join(c for c in badge_el.inner_text().upper() if c.isdigit())
            desconto = int(numeros) if numeros else 0

        preco_el = card.query_selector(
            ".ui-search-price__part:not(.ui-search-price__original-value) .andes-money-amount__fraction"
        )
        preco_atual = extrair_numero(preco_el.inner_text() if preco_el else None)
        if not preco_atual or preco_atual < 5:
            return None

        orig_el = card.query_selector(".ui-search-price__original-value .andes-money-amount__fraction")
        preco_orig = extrair_numero(orig_el.inner_text() if orig_el else None)
        if not preco_orig or preco_orig <= preco_atual:
            preco_orig = preco_atual

        if desconto == 0 and preco_orig > preco_atual:
            desconto = round((1 - preco_atual / preco_orig) * 100)

        link_el = card.query_selector("a.ui-search-link, a.poly-component__title, a[href*='produto.mercadolivre']")
        if not link_el:
            return None
        url = (link_el.get_attribute("href", timeout=3000) or "").split("#")[0].split("?")[0]
        if not url or "mercadolivre" not in url:
            return None

        img_el = card.query_selector("img.ui-search-result-image__element, img.poly-component__picture, img[src*='mlstatic']")
        imagem = ""
        if img_el:
            imagem = (img_el.get_attribute("src") or img_el.get_attribute("data-src") or "")
        imagem = imagem.replace("http://", "https://")
        if not imagem:
            imagem = "https://via.placeholder.com/500x500?text=Oferta"

        return {
            "titulo": titulo, "preco_original": preco_orig,
            "preco_atual": preco_atual, "desconto": desconto,
            "url": url, "imagem": imagem, "link_afiliado": "",
        }
    except Exception:
        return None


def scrape_termo(page, termo, min_off):
    url = f"https://lista.mercadolivre.com.br/{termo.replace(' ', '-')}_PriceDiscount_10-100"
    for tentativa in range(1, 4):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            espera_humana(2, 5)
            scroll_humano(page, vezes=random.randint(2, 4))
            espera_humana(1, 3)
            break
        except Exception as e:
            logger.warning(f"  Tentativa {tentativa}/3 falhou: {e}")
            if tentativa == 3:
                return []
            espera_humana(3, 6)

    cards = page.query_selector_all(".ui-search-result__wrapper")[:MAX_POR_TERMO]
    encontrados = []
    for card in cards:
        oferta = extrair_oferta(card)
        if oferta and oferta["desconto"] >= min_off:
            encontrados.append(oferta)
    logger.info(f"  → {len(encontrados)} oferta(s) com >= {min_off}% OFF")
    return encontrados


def main():
    periodo = periodo_atual()
    buscas = NICHOS[periodo]
    logger.info("=" * 60)
    logger.info(f"PERÍODO: {periodo.upper()} | {len(buscas)} nichos")
    logger.info("=" * 60)

    historico = carregar_historico()
    ja_postadas = set(historico.keys())
    logger.info(f"No histórico (ignoradas): {len(ja_postadas)}")

    vistos, ofertas = set(), []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(**configurar_contexto_stealth())
        page = ctx.new_page()
        aplicar_stealth(page)

        try:
            page.goto("https://www.mercadolivre.com.br", wait_until="domcontentloaded", timeout=30000)
            espera_humana(2, 4)
        except Exception:
            pass

        for i, busca in enumerate(buscas, 1):
            logger.info(f"[{i}/{len(buscas)}] '{busca['q']}' (>={busca['min_off']}% OFF)")
            try:
                for o in scrape_termo(page, busca["q"], busca["min_off"]):
                    if o["url"] not in vistos and o["url"] not in ja_postadas:
                        vistos.add(o["url"])
                        ofertas.append(o)
            except Exception as e:
                logger.error(f"  Erro: {e}")
            espera_humana(4, 9)

        browser.close()

    ofertas.sort(key=lambda o: o["desconto"], reverse=True)
    selecionadas = ofertas[:MAX_FINAL]

    with open("ofertas.json", "w", encoding="utf-8") as f:
        json.dump(selecionadas, f, ensure_ascii=False, indent=2)

    logger.info(f"RESULTADO: {len(selecionadas)} oferta(s) prontas")
    for o in selecionadas:
        logger.info(f"  {o['desconto']:3d}% OFF | R${o['preco_atual']:.2f} | {o['titulo'][:50]}")


if __name__ == "__main__":
    main()
