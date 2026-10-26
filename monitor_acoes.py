"""
Monitor de ações da B3 com alerta por WhatsApp.

Como funciona:
- A cada INTERVALO_SEGUNDOS consulta o preço atual de cada ativo (dados com
  possível atraso de ~15 min, dependendo da fonte).
- Calcula a variação em relação ao fechamento anterior.
- Envia alerta quando a variação cruza um novo "degrau" (ex.: 3%, 6%, -3%...),
  evitando repetir a mesma mensagem toda hora.
- Cada alerta é gravado em alertas.csv (o painel mostra esse histórico).

Ativos e degraus: edite o config.py.

Instalação:
    pip install -r requirements.txt

Configuração (variáveis de ambiente, não escreva senhas no código):
    WHATSAPP_PHONE    seu número com DDI, ex.: 5535999999999
    CALLMEBOT_APIKEY  chave recebida do CallMeBot (veja callmebot.com)

Uso:
    python monitor_acoes.py --test   # envia mensagem de teste
    python monitor_acoes.py          # inicia o monitoramento
"""

import csv
import os
import sys
import time
import datetime as dt

import requests
import yfinance as yf

from config import ATIVOS, ARQ_ALERTAS, TZ

# ----------------------------- CONFIGURAÇÃO -----------------------------

INTERVALO_SEGUNDOS = 300      # consulta a cada 5 minutos
ABERTURA = dt.time(10, 0)     # horário de Brasília
FECHAMENTO = dt.time(17, 55)

CAMPOS_ALERTA = [
    "data_hora", "ticker", "sentido", "variacao_pct",
    "preco", "fechamento_anterior", "whatsapp_enviado",
]

# ------------------------------ ENVIO -----------------------------------


def enviar_whatsapp(texto: str) -> bool:
    """Envia mensagem via CallMeBot (serviço não oficial, uso pessoal).

    Para trocar por Twilio ou pela API oficial da Meta, altere só esta função.
    """
    phone = os.environ.get("WHATSAPP_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    if not phone or not apikey:
        print("Defina WHATSAPP_PHONE e CALLMEBOT_APIKEY.")
        return False
    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": phone, "text": texto, "apikey": apikey},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"Falha no envio ({r.status_code}): {r.text[:200]}")
            return False
        return True
    except requests.RequestException as e:
        print(f"Erro de rede ao enviar: {e}")
        return False


def registrar_alerta(agora, ticker, variacao, preco, anterior, enviado):
    """Acrescenta uma linha em alertas.csv (cria o arquivo se não existir)."""
    try:
        novo = not ARQ_ALERTAS.exists()
        with open(ARQ_ALERTAS, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS_ALERTA)
            if novo:
                w.writeheader()
            w.writerow({
                "data_hora": agora.strftime("%Y-%m-%d %H:%M:%S"),
                "ticker": ticker,
                "sentido": "ALTA" if variacao > 0 else "QUEDA",
                "variacao_pct": round(variacao, 2),
                "preco": round(preco, 2),
                "fechamento_anterior": round(anterior, 2),
                "whatsapp_enviado": "sim" if enviado else "nao",
            })
    except OSError as e:
        print(f"Não foi possível gravar o histórico de alertas: {e}")


# ------------------------------ COTAÇÃO ---------------------------------


def obter_cotacao(ticker: str):
    """Retorna (preco_atual, fechamento_anterior) ou None se falhar."""
    try:
        info = yf.Ticker(f"{ticker}.SA").fast_info
        preco = float(info["last_price"])
        anterior = float(info["previous_close"])
        if preco <= 0 or anterior <= 0:
            return None
        return preco, anterior
    except Exception as e:  # a fonte é não oficial e pode falhar
        print(f"[{ticker}] erro ao obter cotação: {e}")
        return None


def mercado_aberto(agora: dt.datetime) -> bool:
    return agora.weekday() < 5 and ABERTURA <= agora.time() <= FECHAMENTO


# ------------------------------ PRINCIPAL --------------------------------


def main():
    if "--test" in sys.argv:
        ok = enviar_whatsapp("Teste do monitor de ações: funcionando.")
        print("Enviado." if ok else "Não foi possível enviar.")
        return

    print(f"Monitorando: {', '.join(ATIVOS)}")
    enviar_whatsapp(f"Monitor iniciado para: {', '.join(ATIVOS)}")

    nivel_atual = {t: 0 for t in ATIVOS}  # último degrau alertado por ativo
    dia_estado = dt.datetime.now(TZ).date()

    while True:
        agora = dt.datetime.now(TZ)

        # novo dia: zera os degraus
        if agora.date() != dia_estado:
            nivel_atual = {t: 0 for t in ATIVOS}
            dia_estado = agora.date()

        if mercado_aberto(agora):
            for ticker, degrau in ATIVOS.items():
                cot = obter_cotacao(ticker)
                if cot is None:
                    continue
                preco, anterior = cot
                variacao = (preco / anterior - 1) * 100
                nivel = int(variacao / degrau)  # 0, ±1, ±2...

                if nivel != nivel_atual[ticker]:
                    if nivel != 0:
                        sentido = "ALTA" if variacao > 0 else "QUEDA"
                        msg = (
                            f"{ticker}: {sentido} de {variacao:+.2f}% hoje\n"
                            f"Preço: R$ {preco:.2f} "
                            f"(fech. anterior R$ {anterior:.2f})\n"
                            f"{agora:%H:%M}"
                        )
                        print(msg.replace("\n", " | "))
                        enviado = enviar_whatsapp(msg)
                        registrar_alerta(
                            agora, ticker, variacao, preco, anterior, enviado
                        )
                    nivel_atual[ticker] = nivel

        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEncerrado.")
