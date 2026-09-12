"""
Gera tres arquivos HTML standalone — sem servidor, sem Python, sem internet obrigatoria.
  index.html        — dashboard interativo normal (dados embutidos)
  apresentacao.html — apresentacao automatica com transicoes a cada 30s (dados embutidos)
  metas.html        — Check de Metas (apresentacao slide-a-slide com dados embutidos)

Todos funcionam com duplo clique, pen drive, envio por e-mail ou TV.
"""

import json
import os
import re

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raiz do ETL
HTML_SRC  = os.path.join(BASE_DIR, "dashboard.html")
CSS_SRC   = os.path.join(BASE_DIR, "dashboard.css")
JS_SRC    = os.path.join(BASE_DIR, "dashboard.js")
JSON_SRC  = os.path.join(BASE_DIR, "dashboard_data.json")
CHECK_SRC = os.path.join(BASE_DIR, "check_metas.html")
FRESC_SRC = os.path.join(BASE_DIR, "frescal_diretoria.html")
INDEX_OUT = os.path.join(BASE_DIR, "index.html")
APRES_OUT = os.path.join(BASE_DIR, "apresentacao.html")
METAS_OUT = os.path.join(BASE_DIR, "metas.html")
FRESC_OUT = os.path.join(BASE_DIR, "frescal.html")


def _inline_assets(html):
    """Substitui <link stylesheet> e <script src> por seus conteudos inline.

    Necessario para gerar HTMLs standalone que funcionam sem servidor.
    """
    if os.path.exists(CSS_SRC):
        with open(CSS_SRC, encoding="utf-8") as f:
            css = f.read()
        html = html.replace(
            '    <link rel="stylesheet" href="dashboard.css">',
            f"    <style>\n{css}    </style>",
        )

    if os.path.exists(JS_SRC):
        with open(JS_SRC, encoding="utf-8") as f:
            js = f.read()
        html = html.replace(
            '<script src="dashboard.js"></script>',
            f"<script>\n{js}</script>",
        )

    return html


def _embed_data(html, data):
    """Embute o JSON no HTML e substitui o fetch pela variavel embutida (dashboard.html)."""
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    inject   = f"<script>const __DADOS_EMBUTIDOS__={json_str};</script>"
    html     = html.replace("</head>", f"  {inject}\n</head>", 1)

    fetch_pattern = re.compile(
        r"const r = await fetch\('dashboard_data\.json'\);\s*\n\s*DATA = await r\.json\(\);",
        re.MULTILINE,
    )
    html, n = fetch_pattern.subn("DATA = __DADOS_EMBUTIDOS__;", html)
    if n == 0:
        print("  [AVISO] Padrao fetch nao encontrado — verifique dashboard.html.")

    html = html.replace(
        "alert('Erro ao carregar dados. Execute pipeline.py e acesse via http://localhost:8080/dashboard.html')",
        "alert('Erro ao carregar dados. Regenere o arquivo com Gerar_Index.bat.')",
    )
    return html


def _inject_data(html, data):
    """Injeta o JSON como const global antes de </head> (sem mexer no resto).

    Usado por páginas standalone cujo JS já lê __DADOS_EMBUTIDOS__ com fallback
    para fetch — ex.: frescal_diretoria.html.
    """
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    inject   = f"<script>const __DADOS_EMBUTIDOS__={json_str};</script>"
    return html.replace("</head>", f"  {inject}\n</head>", 1)


MESES_PT = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
            "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]

def _embed_data_check(html, data):
    """Embute o JSON no check_metas.html e atualiza opções de mês dinamicamente."""
    # 1) Embute os dados
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    inject   = f"<script>const __DADOS_EMBUTIDOS__={json_str};</script>"
    html     = html.replace("</head>", f"  {inject}\n</head>", 1)

    # 2) Atualiza as opções do <select id="monthSelect"> com os meses reais dos dados
    meses = data.get("filtros", {}).get("meses", [])
    if meses:
        ano_base = meses[0].split("-")[0]
        options  = f'                        <option value="all">Todos os Meses / {ano_base}</option>\n'
        for i, mes in enumerate(meses):
            ano, m = mes.split("-")
            nome   = f"{MESES_PT[int(m)-1]} / {ano}"
            sel    = ' selected' if i == len(meses) - 1 else ''
            options += f'                        <option value="{mes}"{sel}>{nome}</option>\n'
        # Substitui todo o bloco de options dentro do monthSelect
        import re
        html = re.sub(
            r'(<select[^>]*id="monthSelect"[^>]*>)(.*?)(</select>)',
            lambda m2: m2.group(1) + "\n" + options.rstrip() + "\n                    " + m2.group(3),
            html, flags=re.DOTALL
        )
    return html


def main():
    for src in [HTML_SRC, JSON_SRC]:
        if not os.path.exists(src):
            print(f"[ERRO] Arquivo nao encontrado: {src}")
            return False

    print("[1/5] Lendo dados...")
    with open(JSON_SRC, encoding="utf-8") as f:
        data = json.load(f)
    gerado_em = data.get("gerado_em", "?")

    print("[2/5] Lendo dashboard.html + assets...")
    with open(HTML_SRC, encoding="utf-8") as f:
        base_html = f.read()
    base_html = _inline_assets(base_html)

    # ── index.html (interativo) ──────────────────────────────────────────
    print("[3/5] Gerando index.html (interativo)...")
    html_index = _embed_data(base_html, data)
    with open(INDEX_OUT, "w", encoding="utf-8") as f:
        f.write(html_index)
    kb_index = os.path.getsize(INDEX_OUT) / 1024

    # ── apresentacao.html (modo automatico sempre ativo) ─────────────────
    print("[4/5] Gerando apresentacao.html (modo apresentacao sempre ativo)...")
    html_ap = _embed_data(base_html, data)

    # Remove a checagem do parametro URL — apresentacao sempre ligada
    html_ap = html_ap.replace(
        "    const params = new URLSearchParams(window.location.search);\n"
        "    if (!params.has('apresentacao')) return;",
        "    // Modo apresentacao sempre ativo neste arquivo",
    )

    with open(APRES_OUT, "w", encoding="utf-8") as f:
        f.write(html_ap)
    kb_ap = os.path.getsize(APRES_OUT) / 1024

    # ── metas.html (check_metas com dados embutidos) ─────────────────────
    kb_metas = 0
    if os.path.exists(CHECK_SRC):
        print("[5/5] Gerando metas.html (Check de Metas com dados embutidos)...")
        with open(CHECK_SRC, encoding="utf-8") as f:
            check_html = f.read()
        html_metas = _embed_data_check(check_html, data)
        with open(METAS_OUT, "w", encoding="utf-8") as f:
            f.write(html_metas)
        kb_metas = os.path.getsize(METAS_OUT) / 1024
    else:
        print("[5/5] [AVISO] check_metas.html nao encontrado — pulando metas.html.")

    # ── frescal.html (relatorio executivo Frescal para diretoria) ────────
    kb_fresc = 0
    if os.path.exists(FRESC_SRC):
        print("[+]   Gerando frescal.html (relatorio executivo Frescal)...")
        with open(FRESC_SRC, encoding="utf-8") as f:
            fresc_html = f.read()
        html_fresc = _inject_data(fresc_html, data)
        with open(FRESC_OUT, "w", encoding="utf-8") as f:
            f.write(html_fresc)
        kb_fresc = os.path.getsize(FRESC_OUT) / 1024
    else:
        print("[+]   [AVISO] frescal_diretoria.html nao encontrado — pulando frescal.html.")

    print()
    print("=" * 58)
    print(f"  Dados de: {gerado_em}")
    print("=" * 58)
    print(f"  index.html         {kb_index:>6.0f} KB  — uso interativo normal")
    print(f"  apresentacao.html  {kb_ap:>6.0f} KB  — abre ja em apresentacao")
    if kb_metas:
        print(f"  metas.html         {kb_metas:>6.0f} KB  — Check de Metas (slide-a-slide)")
    if kb_fresc:
        print(f"  frescal.html       {kb_fresc:>6.0f} KB  — Relatorio Frescal (diretoria)")
    print("=" * 58)
    print()
    print("  Todos funcionam sem servidor e sem Python.")
    print("  Salve no pen drive ou envie para a TV.")
    print()
    return True


if __name__ == "__main__":
    ok = main()
    if not ok:
        input("\nPressione Enter para sair...")
