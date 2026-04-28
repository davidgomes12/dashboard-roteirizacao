"""
Enviar Dashboard por E-mail — Indicador da Roteirização 2026
Atualiza pipeline, captura screenshots dos dashboards e envia via Outlook.
"""

import subprocess
import sys
import os
import socket
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(BASE_DIR, "pipeline.py")
DEST_EMAIL = "roteirizacao@tirolez.com.br; entregas.capitalsp@tirolez.com.br; Operacao.Logistica@tirolez.com.br; customer.service@tirolez.com.br; pagamentos.logistica@tirolez.com.br"


def kill_port(port):
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue "
             f"| ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass


def wait_port(port, timeout=10):
    for _ in range(timeout * 2):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def capture_screenshots():
    from playwright.sync_api import sync_playwright

    pages_config = [
        ("roteiro",     "Roteiro",     "filterMes",      "filterDia"),
        ("reentregas",  "Reentregas",  "filterMesReent", "filterDiaReent"),
        ("frota",       "Frota",       "filterMesFrota", "filterDiaFrota"),
        ("vespertina",  "Vespertina",  "filterMesVesp",  "filterDiaVesp"),
    ]

    screenshots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            device_scale_factor=1.5,
        )
        page = context.new_page()

        for page_id, page_name, mes_id, dia_id in pages_config:
            print(f"   -> {page_name}...", end=" ", flush=True)
            page.goto("http://localhost:8080/dashboard.html")
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Trocar aba
            page.evaluate(f"""
                document.querySelectorAll('.tab').forEach(t => {{
                    if (t.textContent.trim() === '{page_name}') t.click();
                }});
            """)
            time.sleep(0.5)

            # Selecionar último mês disponível
            month_label = page.evaluate(f"""
                (() => {{
                    const s = document.getElementById('{mes_id}');
                    if (s && s.options.length > 1) {{
                        const opt = s.options[s.options.length - 1];
                        s.value = opt.value;
                        s.dispatchEvent(new Event('change'));
                        return opt.textContent;
                    }}
                    return 'Todos';
                }})()
            """)
            time.sleep(1)

            # Selecionar último dia disponível
            day_label = page.evaluate(f"""
                (() => {{
                    const s = document.getElementById('{dia_id}');
                    if (s && s.options.length > 1) {{
                        const opt = s.options[s.options.length - 1];
                        s.value = opt.value;
                        s.dispatchEvent(new Event('change'));
                        return opt.textContent;
                    }}
                    return '';
                }})()
            """)
            time.sleep(2)  # Espera charts renderizarem

            date_label = f"{day_label} — {month_label}" if day_label else month_label

            path = os.path.join(BASE_DIR, f"_screenshot_{page_id}.png")
            page.screenshot(path=path, full_page=True)
            screenshots.append((page_name, path, date_label))
            print(f"({date_label})")

        browser.close()

    return screenshots


def send_email(screenshots):
    import win32com.client

    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)
    mail.To = DEST_EMAIL
    mail.Subject = f"Indicador da Roteirização — {datetime.now().strftime('%d/%m/%Y')}"

    # Anexar imagens com CID para embedding
    for i, (name, path, _) in enumerate(screenshots):
        att = mail.Attachments.Add(os.path.abspath(path))
        att.PropertyAccessor.SetProperty(
            "http://schemas.microsoft.com/mapi/proptag/0x3712001F",
            f"dash{i}"
        )

    # Montar HTML do e-mail
    sections = ""
    for i, (name, path, date_label) in enumerate(screenshots):
        sections += f"""
        <div style="margin-bottom: 36px;">
            <h2 style="color:#C41419; font-family:'Segoe UI',Arial,sans-serif; font-size:18px;
                border-left:4px solid #F51A20; padding-left:12px; margin-bottom:14px;">
                {name} <span style="color:#888; font-size:14px; font-weight:400;">— {date_label}</span>
            </h2>
            <img src="cid:dash{i}" style="width:100%; max-width:1200px; border-radius:8px;
                box-shadow:0 2px 12px rgba(0,0,0,0.12); display:block;">
        </div>
        """

    mail.HTMLBody = f"""
    <html><body style="margin:0; padding:0; background:#f4f4f4; font-family:'Segoe UI',Arial,sans-serif;">
    <div style="max-width:1240px; margin:0 auto; padding:20px;">
        <div style="background:white; border-radius:12px; overflow:hidden;
            box-shadow:0 2px 16px rgba(0,0,0,0.08);">

            <div style="background:linear-gradient(135deg,#C41419,#F51A20); padding:28px 36px; text-align:center;">
                <h1 style="color:white; margin:0; font-size:22px; font-weight:700; letter-spacing:-0.3px;">
                    Indicador da Roteirização 2026
                </h1>
                <p style="color:rgba(255,255,255,0.75); margin:6px 0 0; font-size:13px;">
                    Logística — Distribuição SP &nbsp;|&nbsp; {datetime.now().strftime('%d/%m/%Y %H:%M')}
                </p>
            </div>

            <div style="padding:32px 36px;">
                {sections}
            </div>

            <div style="background:#f0f0f0; padding:14px 36px; text-align:center;
                font-size:11px; color:#999;">
                Gerado automaticamente pelo sistema de indicadores — Tirolez
            </div>
        </div>
    </div>
    </body></html>
    """

    mail.Send()
    print(f"\n   E-mail enviado para:")
    for addr in DEST_EMAIL.split(";"):
        print(f"     - {addr.strip()}")


def main():
    print("=" * 60)
    print("  ENVIAR DASHBOARD POR E-MAIL")
    print("=" * 60)

    # 1. Pipeline
    print("\n[1/4] Atualizando dados...")
    result = subprocess.run([sys.executable, PIPELINE], cwd=BASE_DIR)
    if result.returncode != 0:
        print("[ERRO] Pipeline falhou.")
        return False

    # 2. Servidor
    print("\n[2/4] Iniciando servidor...")
    kill_port(8080)
    time.sleep(1)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8080"],
        cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=0x08000000  # CREATE_NO_WINDOW
    )
    if not wait_port(8080):
        print("[ERRO] Servidor não iniciou.")
        server.terminate()
        return False

    # 3. Screenshots
    print("\n[3/4] Capturando dashboards...")
    try:
        screenshots = capture_screenshots()
    except Exception as e:
        print(f"[ERRO] Captura falhou: {e}")
        server.terminate()
        return False
    finally:
        server.terminate()

    # 4. E-mail
    print("\n[4/4] Enviando e-mail...")
    try:
        send_email(screenshots)
    except Exception as e:
        print(f"[ERRO] Envio falhou: {e}")
        print("   Verifique se o Outlook está aberto e configurado.")
        return False
    finally:
        # Limpar screenshots
        for _, path, _ in screenshots:
            try:
                os.remove(path)
            except OSError:
                pass

    print("\n" + "=" * 60)
    print("  CONCLUÍDO!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    if not success:
        input("\nPressione Enter para sair...")
