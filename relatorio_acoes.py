"""
Relatório de variação das ações: último pregão, 7 dias, 1 mês e 3 meses.

Uso (na mesma pasta dos demais arquivos):
    python relatorio_acoes.py             # mostra o relatório na tela
    python relatorio_acoes.py --enviar    # também manda resumo no WhatsApp

Observações:
- Usa o preço de fechamento SEM ajuste por proventos. Ou seja, em ações que
  pagam muito dividendo (ex.: TAEE11), a queda no dia "ex-dividendo" aparece
  como variação de preço, mesmo que o investidor tenha recebido o provento.
- "24h" = variação do último pregão contra o pregão anterior (a bolsa não
  negocia 24h). Períodos de 7d/1m/3m são em dias corridos: usa o último
  fechamento disponível na data de referência ou antes dela.
- Dados da yfinance (fonte não oficial): confira números importantes em
  fonte oficial ou na sua corretora.
"""

import sys
import datetime as dt

import pandas as pd
import yfinance as yf

from config import ATIVOS as _ATIVOS, INDICE, TZ

ATIVOS = list(_ATIVOS)
REFERENCIA = INDICE

# nome do período -> dias corridos (None = pregão anterior)
PERIODOS = {"24h": None, "7d": 7, "1m": 30, "3m": 90}


def variacao(serie: pd.Series, dias):
    """Variação percentual do último fechamento contra a referência."""
    if serie is None or len(serie) < 2:
        return None
    ultimo = serie.iloc[-1]
    if dias is None:
        ref = serie.iloc[-2]
    else:
        limite = serie.index[-1] - pd.Timedelta(days=dias)
        anteriores = serie[serie.index <= limite]
        if anteriores.empty:
            return None  # histórico insuficiente
        ref = anteriores.iloc[-1]
    if ref <= 0:
        return None
    return (ultimo / ref - 1) * 100


def baixar_fechamentos(simbolo: str):
    try:
        h = yf.Ticker(simbolo).history(period="6mo", auto_adjust=False)
        s = h["Close"].dropna()
        return s if len(s) >= 2 else None
    except Exception as e:
        print(f"[{simbolo}] erro ao baixar dados: {e}")
        return None


def fmt(v):
    return "  n/d " if v is None else f"{v:+6.2f}%"


def montar_relatorio():
    itens = [(t, f"{t}.SA") for t in ATIVOS] + [(REFERENCIA[1], REFERENCIA[0])]
    linhas = []
    msg = []
    for nome, simbolo in itens:
        s = baixar_fechamentos(simbolo)
        if s is None:
            linhas.append(f"{nome:<10} sem dados")
            msg.append(f"{nome}: sem dados")
            continue
        vars_ = {p: variacao(s, d) for p, d in PERIODOS.items()}
        preco = s.iloc[-1]
        linhas.append(
            f"{nome:<10} {preco:>10.2f}  "
            + "  ".join(fmt(vars_[p]) for p in PERIODOS)
        )
        msg.append(
            f"{nome} {preco:.2f} | "
            + " ".join(
                f"{p} {'n/d' if vars_[p] is None else format(vars_[p], '+.1f') + '%'}"
                for p in PERIODOS
            )
        )

    cab = f"{'Ativo':<10} {'Último':>10}  " + "  ".join(f"{p:>7}" for p in PERIODOS)
    titulo = (
        f"Relatório de variação - gerado em {dt.datetime.now(TZ):%d/%m/%Y %H:%M}"
    )
    tela = "\n".join([titulo, "", cab, "-" * len(cab)] + linhas)
    return tela, titulo + "\n" + "\n".join(msg)


if __name__ == "__main__":
    tela, resumo = montar_relatorio()
    print(tela)
    if "--enviar" in sys.argv:
        try:
            from monitor_acoes import enviar_whatsapp
        except ImportError:
            print("Coloque este arquivo na mesma pasta do monitor_acoes.py.")
        else:
            print("Enviado." if enviar_whatsapp(resumo) else "Falha no envio.")
