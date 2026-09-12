"""
Servidor de Apresentacao + Tunel — Dashboard Roteirizacao 2026
  • HTTP na porta 5050 (rede local)
  • Cloudflare Quick Tunnel (URL publica para outras redes / TVs)
  • Bloqueia suspensao, hibernacao, tela e acao da tampa
  • Pagina de compartilhamento com QR code atualizado automaticamente
"""

import ctypes
import http.server
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORT      = 5050
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raiz do ETL
CF_EXE    = os.path.join(BASE_DIR, "bin", "cloudflared.exe")
CF_URL    = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
SHARE_FILE = os.path.join(BASE_DIR, "_conectar.html")

_public_url  = ""   # preenchido pela thread do tunel
_tunnel_proc = None

# ─────────────────────────────────────────────────────────
#  ANTI-SUSPENSAO
# ─────────────────────────────────────────────────────────
_ES_CONTINUOUS       = 0x80000000
_ES_SYSTEM_REQUIRED  = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002
_LID_SUBGROUP = "4f971e89-eebd-4455-a8de-9e59040e7347"
_LID_SETTING  = "5ca83367-6e45-459f-a27b-476b1d01c936"
_lid_ac_orig  = 1
_lid_dc_orig  = 1


def _pcfg(*args):
    # Modo binário — evita _readerthread com cp1252 no Python 3.14
    try:
        return subprocess.run(
            ["powercfg"] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None


def prevent_sleep():
    global _lid_ac_orig, _lid_dc_orig
    ctypes.windll.kernel32.SetThreadExecutionState(
        _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED)
    try:
        r = _pcfg("/query", "SCHEME_CURRENT", _LID_SUBGROUP, _LID_SETTING)
        if r and r.stdout:
            txt = r.stdout.decode("utf-8", errors="replace")
            ac = re.search(r"Current AC.*?:\s+0x([0-9a-fA-F]+)", txt)
            dc = re.search(r"Current DC.*?:\s+0x([0-9a-fA-F]+)", txt)
            _lid_ac_orig = int(ac.group(1), 16) if ac else 1
            _lid_dc_orig = int(dc.group(1), 16) if dc else 1
        _pcfg("-setacvalueindex", "SCHEME_CURRENT", _LID_SUBGROUP, _LID_SETTING, "0")
        _pcfg("-setdcvalueindex", "SCHEME_CURRENT", _LID_SUBGROUP, _LID_SETTING, "0")
        _pcfg("-SetActive", "SCHEME_CURRENT")
    except Exception:
        pass


def restore_sleep():
    ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    try:
        _pcfg("-setacvalueindex", "SCHEME_CURRENT", _LID_SUBGROUP, _LID_SETTING, str(_lid_ac_orig))
        _pcfg("-setdcvalueindex", "SCHEME_CURRENT", _LID_SUBGROUP, _LID_SETTING, str(_lid_dc_orig))
        _pcfg("-SetActive", "SCHEME_CURRENT")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────
#  SERVIDOR HTTP
# ─────────────────────────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):
    # HTTP/1.1 obrigatório para o Cloudflare Tunnel funcionar corretamente
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        super().do_GET()

    def log_message(self, fmt, *args):
        req = str(args[0])
        if any(req.endswith(ext) for ext in (".png", ".ico", ".woff", ".woff2", ".css", "tunnel_url")):
            return
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] {self.address_string():>16}  {req}", flush=True)


# ─────────────────────────────────────────────────────────
#  TUNEL CLOUDFLARE
# ─────────────────────────────────────────────────────────
def _download_cloudflared():
    print()
    print("  cloudflared.exe nao encontrado. Baixando (~35 MB)...")
    tmp = CF_EXE + ".tmp"

    def _prog(count, block, total):
        if total <= 0:
            return
        pct = min(int(count * block * 100 / total), 100)
        bar = "#" * (pct // 4) + "." * (25 - pct // 4)
        mb  = min(count * block / 1_048_576, total / 1_048_576)
        print(f"\r  [{bar}] {pct:3d}%  {mb:.1f}/{total/1_048_576:.1f} MB",
              end="", flush=True)

    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        urllib.request.install_opener(opener)

        req = urllib.request.Request(CF_URL)
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            block = 65536
            count = 0
            while True:
                chunk = resp.read(block)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                count += 1
                _prog(count, block, total)

        os.replace(tmp, CF_EXE)
        print("\n  Download concluido!\n")
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(
            f"Falha ao baixar cloudflared.exe: {e}\n"
            "  Baixe manualmente em: https://github.com/cloudflare/cloudflared/releases/latest\n"
            "  e coloque o arquivo cloudflared-windows-amd64.exe na pasta bin/ renomeado para cloudflared.exe"
        ) from e


def _drain(proc):
    """Consome o output restante do cloudflared para o pipe nao encher e o processo nao travar."""
    try:
        for _ in iter(proc.stdout.readline, b""):
            pass
    except Exception:
        pass


def _tunnel_worker(url_rede):
    global _public_url, _tunnel_proc
    try:
        if not os.path.exists(CF_EXE):
            try:
                _download_cloudflared()
            except RuntimeError as e:
                print(f"\n\n  [AVISO] {e}\n")
                print("  Tunel desativado. Rede local continua funcionando.\n")
                return

        # Modo binario puro — sem text=True, sem encoding, sem _readerthread interno
        _tunnel_proc = subprocess.Popen(
            [CF_EXE, "tunnel", "--url", f"http://localhost:{PORT}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        print("  Tunel: aguardando URL", end="", flush=True)

        for raw in iter(_tunnel_proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace")
            print(".", end="", flush=True)
            match = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
            if match:
                _public_url = match.group(0)
                break

        # Mantém processo vivo; drena output em background para não encher o pipe
        if _tunnel_proc.poll() is None:
            threading.Thread(target=_drain, args=(_tunnel_proc,), daemon=True).start()

        if _public_url:
            url_tv = _public_url + "/dashboard.html?apresentacao"
            print(f"\n\n  [TUNEL ATIVO]")
            print(f"  URL publica (TVs / outras redes): {url_tv}")
            print(f"  Abrindo pagina de compartilhamento...\n")
            create_share_page(url_rede, url_tv)
            time.sleep(0.5)
            webbrowser.open(f"http://localhost:{PORT}/_conectar.html")
        else:
            print("\n  [AVISO] Tunel nao retornou URL. Rede local continua funcionando.\n")

    except Exception as e:
        print(f"\n  [AVISO] Tunel falhou: {e}. Rede local continua funcionando.\n")


# ─────────────────────────────────────────────────────────
#  PAGINA DE COMPARTILHAMENTO
# ─────────────────────────────────────────────────────────
_SHARE_HTML = """\
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Conectar ao Dashboard - Tirolez</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', Arial, sans-serif;
      background: linear-gradient(135deg, #fff4ee 0%, #fff0e8 100%);
      min-height: 100vh; display: flex; align-items: center;
      justify-content: center; padding: 20px;
    }
    .card {
      background: #fff; border-radius: 20px;
      box-shadow: 0 8px 40px rgba(196,20,25,.15);
      padding: 36px 44px; max-width: 480px; width: 100%;
      display: flex; flex-direction: column; align-items: center; gap: 18px;
    }
    h1 { font-size: 1.15rem; color: #1c1c2e; font-weight: 700; text-align: center; }
    canvas { border-radius: 12px; border: 3px solid #C41419; }
    .url-box {
      width: 100%; background: #fff4ee; border: 2px solid #C41419; border-radius: 10px;
      padding: 10px 14px; font-size: 0.78rem; color: #333;
      word-break: break-all; line-height: 1.4; text-align: center;
    }
    .btns { display: flex; gap: 8px; width: 100%; }
    button {
      flex: 1; padding: 11px; border: none; border-radius: 8px;
      font-size: 0.83rem; font-weight: 600; cursor: pointer; transition: filter .2s;
    }
    button:hover { filter: brightness(0.88); }
    .btn-red  { background: #C41419; color: #fff; }
    .btn-gray { background: #f0f0f0; color: #333; }
    .divider {
      width: 100%; text-align: center; font-size: 0.7rem; font-weight: 700;
      color: #aaa; text-transform: uppercase; letter-spacing: 0.8px;
      border-top: 1px solid #eee; padding-top: 14px;
    }
    .local-url {
      width: 100%; background: #f8f8f8; border: 1px solid #ddd; border-radius: 8px;
      padding: 8px 12px; font-size: 0.74rem; color: #666;
      word-break: break-all; text-align: center;
    }
    .warn {
      font-size: 0.7rem; color: #D97706; background: #FFF8E7;
      border: 1px solid #FDE68A; border-radius: 8px;
      padding: 7px 12px; text-align: center; width: 100%;
    }
    .status { font-size: 0.72rem; color: #16A34A; font-weight: 600; min-height: 16px; }
  </style>
</head>
<body>
<div class="card">
  <h1>Dashboard da Roteirizacao 2026</h1>

  <canvas id="qr"></canvas>

  <div class="url-box" id="tunnel-url">__TUNNEL_URL__</div>

  <div class="btns">
    <button class="btn-red"  onclick="copy('tunnel-url')">Copiar Link</button>
    <button class="btn-gray" onclick="window.open(document.getElementById('tunnel-url').textContent.trim(),'_blank')">Abrir</button>
  </div>

  <div class="warn">URL temporaria - expira ao encerrar o servidor</div>

  <div class="divider">Mesma rede Wi-Fi / LAN</div>
  <div class="local-url" id="local-url">__LOCAL_URL__</div>
  <button class="btn-gray" style="width:100%" onclick="copy('local-url')">Copiar link da rede local</button>

  <div class="status" id="status"></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.4/build/qrcode.min.js"></script>
<script>
  QRCode.toCanvas(
    document.getElementById('qr'),
    '__TUNNEL_URL__',
    { width: 270, margin: 2, color: { dark: '#C41419', light: '#FFFFFF' } }
  );
  function copy(id) {
    navigator.clipboard.writeText(document.getElementById(id).textContent.trim()).then(() => {
      document.getElementById('status').textContent = 'Link copiado!';
      setTimeout(() => { document.getElementById('status').textContent = ''; }, 2500);
    });
  }
</script>
</body>
</html>
"""


def create_share_page(local_url, tunnel_url):
    html = (_SHARE_HTML
            .replace("__TUNNEL_URL__", tunnel_url)
            .replace("__LOCAL_URL__", local_url))
    with open(SHARE_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def remove_share_page():
    try:
        os.remove(SHARE_FILE)
    except OSError:
        pass


# ─────────────────────────────────────────────────────────
#  REDE
# ─────────────────────────────────────────────────────────
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ─────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────
def main():
    ip        = get_local_ip()
    url_local = f"http://localhost:{PORT}/dashboard.html?apresentacao"
    url_rede  = f"http://{ip}:{PORT}/dashboard.html?apresentacao"
    url_share = f"http://localhost:{PORT}/_conectar.html"

    # Servidor HTTP com suporte a múltiplas conexões simultâneas (necessário para o túnel)
    try:
        server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    except OSError:
        print(f"\n  [ERRO] Porta {PORT} ja esta em uso.\n")
        input("Pressione Enter para sair...")
        return

    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    # Anti-suspensao
    prevent_sleep()

    # Tunel em background — cria a pagina e abre o browser so apos URL estar pronta
    t_thread = threading.Thread(target=_tunnel_worker, args=(url_rede,), daemon=True)
    t_thread.start()

    print()
    print("=" * 64)
    print("  SERVIDOR DE APRESENTACAO - ROTEIRIZACAO 2026")
    print("=" * 64)
    print()
    print(f"  Dashboard (esta maquina)  :  {url_local}")
    print(f"  Dashboard (rede local)    :  {url_rede}")
    print(f"  Tunel publico             :  aguardando Cloudflare...")
    print(f"  QR code / compartilhar    :  abre automaticamente quando o tunel ficar pronto")
    print()
    print("  Protecoes ativas:")
    print("    [OK] Sistema nao suspende nem hiberna")
    print("    [OK] Tela nao apaga automaticamente")
    print("    [OK] Tampa do notebook sem acao")
    print()
    print("  Pressione Ctrl+C para encerrar tudo.")
    print("=" * 64)
    print()
    print("  Acessos recebidos:")

    time.sleep(0.8)
    webbrowser.open(url_local)  # Abre dashboard local imediatamente

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n  Encerrando...")
        if _tunnel_proc:
            _tunnel_proc.terminate()
        server.shutdown()
        restore_sleep()
        remove_share_page()
        print("  Configuracoes de energia restauradas.")
        print("  Encerrado.\n")


if __name__ == "__main__":
    main()
