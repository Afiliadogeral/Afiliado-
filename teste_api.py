
import requests, json, sys

print("="*60)
print("DIAGNÓSTICO: Testando acesso ao Mercado Livre")
print("="*60)

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

testes = [
    # API pública ML (sem auth)
    ("API ML publica", "GET", "https://api.mercadolibre.com/sites/MLB/search?q=whey+protein&limit=3", {}),
    # API com tag on_sale
    ("API ML on_sale", "GET", "https://api.mercadolibre.com/sites/MLB/search?q=whey&limit=3&tag=on_sale", {}),
    # Página HTML simples
    ("HTML lista.ML", "GET", "https://lista.mercadolivre.com.br/whey-protein", HEADERS_BROWSER),
    # Página de ofertas
    ("HTML ofertas ML", "GET", "https://www.mercadolivre.com.br/ofertas", HEADERS_BROWSER),
    # API alternativa
    ("API trends ML", "GET", "https://api.mercadolibre.com/trends/MLB", {}),
    # API categorias
    ("API categorias", "GET", "https://api.mercadolibre.com/sites/MLB/categories", {}),
]

resultados = {}
for nome, metodo, url, hdrs in testes:
    try:
        r = requests.get(url, headers=hdrs, timeout=10)
        status = r.status_code
        tamanho = len(r.text)
        
        # Verifica se tem conteúdo útil
        tem_produto = False
        if status == 200:
            if "results" in r.text and tamanho > 500:
                tem_produto = True
            elif "ui-search-layout__item" in r.text:
                tem_produto = True
            elif '"id":"MLB' in r.text:
                tem_produto = True
        
        resultados[nome] = {
            "status": status,
            "tamanho": tamanho,
            "tem_produto": tem_produto
        }
        
        print(f"\n[{nome}]")
        print(f"  Status: {status} | Tamanho: {tamanho} bytes | Tem produto: {tem_produto}")
        
        if status == 200 and tem_produto:
            print(f"  ✅ FUNCIONA! Amostra: {r.text[:200]}")
        else:
            print(f"  ❌ Amostra: {r.text[:100]}")
            
    except Exception as e:
        print(f"\n[{nome}] ERRO: {e}")
        resultados[nome] = {"erro": str(e)}

print("\n" + "="*60)
print("RESUMO:")
for nome, res in resultados.items():
    ok = res.get("tem_produto", False)
    print(f"  {'✅' if ok else '❌'} {nome}: {res.get('status','ERRO')}")
print("="*60)

# Salva resultado
with open("resultado_diagnostico.json", "w") as f:
    json.dump(resultados, f, indent=2)
print("Resultado salvo em resultado_diagnostico.json")
