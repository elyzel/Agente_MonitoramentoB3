"""
Configuração central. Edite aqui e todos os programas passam a usar.

Arquivos do projeto (todos na MESMA pasta):
    config.py            este arquivo
    monitor_acoes.py     alertas por WhatsApp (fica ligado o dia todo)
    relatorio_acoes.py   relatório de variação (24h, 7d, 1m, 3m)
    painel.py            painel web (Streamlit)
    requirements.txt     bibliotecas necessárias
Arquivos criados automaticamente:
    alertas.csv          histórico de alertas enviados
    carteira.csv         suas operações (compras e vendas)
    backups/             cópias de segurança da carteira
"""

from pathlib import Path
from zoneinfo import ZoneInfo

PASTA = Path(__file__).resolve().parent

# ticker -> degrau de variação (%) que dispara alerta no monitor
ATIVOS = {
    "BBAS3": 3.0,
    "ITUB4": 3.0,
    "VALE3": 3.0,
    "PETR4": 3.0,
    "TAEE11": 2.0,  # transmissora de energia, costuma oscilar menos
}

# (símbolo na fonte de dados, nome de exibição)
INDICE = ("^BVSP", "Ibovespa")

ARQ_ALERTAS = PASTA / "alertas.csv"
ARQ_CARTEIRA = PASTA / "carteira.csv"
PASTA_BACKUPS = PASTA / "backups"

TZ = ZoneInfo("America/Sao_Paulo")
