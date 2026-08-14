"""
utils.py — Camada de invisibilidade do bot
==========================================
Contém tudo que faz o bot parecer humano:
  - Rotação de user-agent e fingerprints
  - JavaScript stealth (remove rastros de automação)
  - Delays com padrão humano (aceleração/desaceleração)
  - Gerenciamento de sessão do Instagram entre execuções
"""

import json
import os
import pickle
import random
import time
from datetime import datetime

# ── Pool de user-agents reais de navegadores atuais ───────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 800},
    {"width": 1536, "height": 864},
]

# Script que injeta no navegador antes de qualquer página carregar.
# Remove TODOS os rastros comuns de detecção de bot.
STEALTH_JS = """
// 1. Remove flag webdriver (principal rastro de Selenium/Playwright)
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. Plugins reais (browser real tem plugins, bot não tem)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin',   filename: 'internal-pdf-viewer',  length: 1 },
            { name: 'Chrome PDF Viewer',   filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', length: 1 },
            { name: 'Native Client',       filename: 'internal-nacl-plugin',  length: 2 },
        ];
        plugins.item     = (i) => plugins[i];
        plugins.namedItem = (n) => plugins.find(p => p.name === n);
        plugins.refresh  = () => {};
        plugins.length   = plugins.length;
        return plugins;
    }
});

// 3. Idiomas naturais
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });

// 4. Propriedades de hardware realistas
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8  });

// 5. Chrome runtime (ausente = bot detectado)
if (!window.chrome) {
    window.chrome = { runtime: { id: undefined, connect: () => {}, sendMessage: () => {} } };
}

// 6. Canvas fingerprint — randomização leve para ser único por sessão
const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx) {
        const shift = Math.floor(Math.random() * 5) - 2;
        ctx.fillStyle = `rgba(${shift},${shift},${shift},0.01)`;
        ctx.fillRect(0, 0, 1, 1);
    }
    return _toDataURL.apply(this, arguments);
};

// 7. WebGL vendor/renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Intel Inc.';
    if (param === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};

// 8. Permissions API (bot costuma retornar denied para tudo)
const _query = navigator.permissions && navigator.permissions.query;
if (_query) {
    navigator.permissions.query = (param) => {
        if (param.name === 'notifications') return Promise.resolve({ state: 'prompt' });
        return _query.call(navigator.permissions, param);
    };
}
"""


def configurar_contexto_stealth():
    """Retorna kwargs para browser.new_context() com configuração stealth aleatória."""
    ua = random.choice(USER_AGENTS)
    vp = random.choice(VIEWPORTS)
    return dict(
        user_agent=ua,
        viewport=vp,
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        extra_http_headers={
            "Accept-Language":           "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "none",
            "Sec-Fetch-User":            "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control":             "max-age=0",
        },
    )


def aplicar_stealth(page):
    """Injeta o script de stealth antes de qualquer carregamento."""
    page.add_init_script(STEALTH_JS)


def espera_humana(minimo=1.0, maximo=4.0):
    """Delay com curva de aceleração/desaceleração — mais humano que random uniforme."""
    # Usa distribuição beta pra concentrar tempos no meio do intervalo
    t = minimo + (maximo - minimo) * random.betavariate(2, 2)
    time.sleep(t)


def digitar_humanamente(page_element, texto, delay_min=40, delay_max=140):
    """Digita texto como humano — velocidade variável, às vezes 'corrige' letra."""
    for char in texto:
        page_element.type(char, delay=random.randint(delay_min, delay_max))
    espera_humana(0.3, 0.8)


def scroll_humano(page, vezes=2):
    """Faz scroll progressivo como humano lendo a página."""
    for _ in range(vezes):
        delta = random.randint(200, 600)
        page.mouse.wheel(0, delta)
        espera_humana(0.5, 1.5)


def mascarar_log(texto):
    """Remove dados sensíveis de logs (senhas, tokens, emails)."""
    import re
    texto = re.sub(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', '[EMAIL]', texto)
    texto = re.sub(r'(password|senha|token|apikey|secret|proxy)[^\s]*', r'\1=[OCULTO]', texto, flags=re.IGNORECASE)
    return texto


# ── Gerenciamento de sessão Instagram ────────────────────────────────────────

SESSAO_IG_PATH = "/tmp/ig_sessao.json"

def salvar_sessao_instagram(cl):
    """Salva configurações da sessão para não logar novamente na próxima execução."""
    try:
        settings = cl.get_settings()
        with open(SESSAO_IG_PATH, "w") as f:
            json.dump(settings, f)
        print("  [IG] Sessão salva.")
    except Exception as e:
        print(f"  [IG] Não foi possível salvar sessão: {e}")


def carregar_sessao_instagram(cl):
    """Tenta carregar sessão salva. Retorna True se bem-sucedido."""
    if not os.path.exists(SESSAO_IG_PATH):
        return False
    try:
        with open(SESSAO_IG_PATH) as f:
            settings = json.load(f)
        cl.set_settings(settings)
        return True
    except Exception:
        return False


# ── Período do dia ────────────────────────────────────────────────────────────

def periodo_atual():
    """
    Retorna o período baseado na variável PERIODO do ambiente (definida pelo
    GitHub Actions) ou calcula pelo horário atual se não estiver definida.
    """
    periodo = os.getenv("PERIODO", "").lower()
    if periodo in ("manha", "tarde", "noite"):
        return periodo

    # Fallback: calcula pelo horário de Brasília (UTC-3)
    hora_brt = (datetime.utcnow().hour - 3) % 24
    if   5  <= hora_brt < 12:  return "manha"
    elif 12 <= hora_brt < 18:  return "tarde"
    else:                       return "noite"
