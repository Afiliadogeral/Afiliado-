"""
gerar_links.py — Geração automática de links de afiliado
=========================================================
Faz login no portal de afiliados do Mercado Livre usando Playwright
stealth e gera o link de afiliado para cada produto scrapeado.

Se o login falhar (captcha, 2FA, etc.), usa um fallback inteligente
que adiciona os parâmetros de rastreamento diretamente na URL.
"""

import json
import os
import random
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
from utils import (
    configurar_contexto_stealth, aplicar_stealth,
    espera_humana, digitar_humanamente, mascarar_log
)

load_dotenv()

ML_EMAIL    = os.getenv("ML_EMAIL", "")
ML_PASSWORD = os.getenv("ML_PASSWORD", "")
ETIQUETA    = os.getenv("ETIQUETA_AFILIADO", "rafaelrafa13")

PORTAL_URL  = "https://afiliados.mercadolivre.com.br"
GERADOR_URL = "https://afiliados.mercadolivre.com.br/tools/link-generator"


def link_fallback(url):
    """
    Fallback: constrói a URL com parâmetros de rastreamento da etiqueta.
    Funciona para contabilizar cliques mesmo sem o link curto oficial.
    """
    sep = "&" if "?" in url else "?"
    return (
        f"{url}{sep}matt_tool=60085"
        f"&matt_word={ETIQUETA}"
        f"&matt_source=gg_mlb"
        f"&matt_campaign_id={ETIQUETA}"
        f"&matt_ad_group_id=organico"
    )


def fazer_login(page):
    print("  Acessando portal de afiliados...")
    try:
        page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45000)
        espera_humana(3, 6)
    except PWTimeout:
        print("  [timeout] Portal de afiliados demorou muito.")
        return False

    # Se já redirecionou para dentro do portal, já está logado
    if "afiliados.mercadolivre" in page.url and "/login" not in page.url:
        print("  Já estava logado (sessão ativa).")
        return True

    # Step 1: email
    try:
        campo = page.wait_for_selector(
            "input#user_id, input[name='user_id'], input[type='email'], input[placeholder*='mail']",
            timeout=15000
        )
        campo.click()
        espera_humana(0.5, 1.5)
        digitar_humanamente(campo, ML_EMAIL)
        espera_humana(0.5, 1.0)
        page.keyboard.press("Enter")
        espera_humana(2, 4)
    except PWTimeout:
        print("  [aviso] Campo de email não encontrado.")

    # Step 2: senha
    try:
        campo_s = page.wait_for_selector(
            "input#password, input[name='password'], input[type='password']",
            timeout=15000
        )
        campo_s.click()
        espera_humana(0.5, 1.2)
        digitar_humanamente(campo_s, ML_PASSWORD)
        espera_humana(0.5, 1.0)
        page.keyboard.press("Enter")
        espera_humana(4, 7)
    except PWTimeout:
        print("  [aviso] Campo de senha não encontrado.")
        return False

    # Verifica
    if "/login" in page.url or "password" in page.url:
        print("  [erro] Login falhou.")
        return False

    print("  Login OK.")
    return True


def gerar_um_link(page, url_produto):
    """Gera o link de afiliado para um produto no gerador do portal."""
    try:
        page.goto(GERADOR_URL, wait_until="domcontentloaded", timeout=30000)
        espera_humana(2, 4)

        # Campo de entrada
        campo = page.wait_for_selector(
            "input[placeholder*='URL'], input[placeholder*='url'], "
            "input[placeholder*='link'], textarea[placeholder*='URL'], "
            "input[type='text']:not([readonly])",
            timeout=10000
        )
        campo.triple_click()
        espera_humana(0.2, 0.5)
        campo.fill("")
        digitar_humanamente(campo, url_produto)
        espera_humana(0.5, 1.5)

        # Botão gerar
        btn = page.query_selector(
            "button[type='submit'], "
            "button:has-text('Gerar'), button:has-text('Generar'), "
            "button:has-text('Generate'), button:has-text('Criar')"
        )
        if btn:
            btn.click()
        else:
            page.keyboard.press("Enter")

        espera_humana(2, 4)

        # Pega o link gerado
        for seletor in [
            "input[readonly]",
            "[class*='result'] input",
            "[class*='output'] input",
            "[class*='generated'] input",
            "input[value*='meli.la']",
            "input[value*='mercadolivre']",
        ]:
            el = page.query_selector(seletor)
            if el:
                val = el.get_attribute("value") or el.input_value()
                if val and val.startswith("http"):
                    return val

    except Exception as e:
        print(f"    [gerador] erro: {e}")

    return None


def main():
    with open("ofertas.json", "r", encoding="utf-8") as f:
        ofertas = json.load(f)

    if not ofertas:
        print("Nenhuma oferta para processar.")
        return

    # Sem credenciais → fallback direto
    if not ML_EMAIL or not ML_PASSWORD:
        print("[aviso] ML_EMAIL ou ML_PASSWORD não configurados → links fallback.")
        for o in ofertas:
            o["link_afiliado"] = link_fallback(o["url"])
        with open("ofertas.json", "w", encoding="utf-8") as f:
            json.dump(ofertas, f, ensure_ascii=False, indent=2)
        print(f"✅ {len(ofertas)} links fallback gerados.")
        return

    print(f"Gerando links de afiliado para {len(ofertas)} produto(s)...")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx  = browser.new_context(**configurar_contexto_stealth())
        page = ctx.new_page()
        aplicar_stealth(page)

        logado = fazer_login(page)
        erros  = 0

        for i, oferta in enumerate(ofertas, 1):
            print(f"  [{i}/{len(ofertas)}] {oferta['titulo'][:50]}...")

            link = None
            if logado:
                link = gerar_um_link(page, oferta["url"])

            if link:
                oferta["link_afiliado"] = link
                print(f"    ✅ {link[:60]}")
            else:
                oferta["link_afiliado"] = link_fallback(oferta["url"])
                erros += 1
                print(f"    ⚠️  fallback aplicado")

            espera_humana(2, 5)

        browser.close()

    with open("ofertas.json", "w", encoding="utf-8") as f:
        json.dump(ofertas, f, ensure_ascii=False, indent=2)

    oficiais = len(ofertas) - erros
    print(f"\n✅ {oficiais} link(s) oficial(is) + {erros} fallback(s).")


if __name__ == "__main__":
    main()
