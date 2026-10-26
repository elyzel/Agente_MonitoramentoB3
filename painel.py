"""
Painel web das ações (Streamlit).

Abas: Visão geral | Gráficos | Carteira | Fundamentalistas | Alertas

Como abrir (na pasta dos arquivos):
    streamlit run painel.py --server.address 0.0.0.0 --server.port 8501

Depois, no navegador do computador ou do celular (mesma rede Wi-Fi):
    http://IP-DO-COMPUTADOR-OU-RASPBERRY:8501

ATENÇÃO: o painel não tem senha. Quem estiver na sua rede consegue ver a
carteira e registrar/apagar operações.

Dados de mercado vêm da yfinance (fonte não oficial, com possível atraso).
Nada aqui é recomendação de investimento.
"""

import datetime as dt
import shutil

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from config import (
    ARQ_ALERTAS, ARQ_CARTEIRA, ATIVOS, INDICE, PASTA_BACKUPS, TZ,
)
from relatorio_acoes import variacao

COLUNAS = ["data", "ticker", "tipo", "quantidade", "preco", "taxas"]
MAX_BACKUPS = 30


# ------------------------------ FORMATAÇÃO -------------------------------


def brl(v):
    if v is None or pd.isna(v):
        return "n/d"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def pct(v, sinal=True):
    if v is None or pd.isna(v):
        return "n/d"
    return f"{v:+.2f}%" if sinal else f"{v:.2f}%"


def simb(ticker):
    return ticker if ticker.startswith("^") else f"{ticker}.SA"


# ------------------------------ CARTEIRA (ARQUIVO) -----------------------


def carteira_vazia():
    return pd.DataFrame({
        "data": pd.Series(dtype="datetime64[ns]"),
        "ticker": pd.Series(dtype="object"),
        "tipo": pd.Series(dtype="object"),
        "quantidade": pd.Series(dtype="float64"),
        "preco": pd.Series(dtype="float64"),
        "taxas": pd.Series(dtype="float64"),
    })


def carregar_carteira():
    if not ARQ_CARTEIRA.exists():
        return carteira_vazia()
    df = pd.read_csv(ARQ_CARTEIRA)
    if df.empty:
        return carteira_vazia()
    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    for c in ("quantidade", "preco", "taxas"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["tipo"] = df["tipo"].astype(str).str.lower().str.strip()
    return (
        df[COLUNAS]
        .sort_values(["data", "tipo"], kind="stable")
        .reset_index(drop=True)
    )


def salvar_carteira(df):
    """Grava a carteira, guardando antes uma cópia de segurança."""
    if ARQ_CARTEIRA.exists():
        PASTA_BACKUPS.mkdir(exist_ok=True)
        carimbo = dt.datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
        shutil.copy2(ARQ_CARTEIRA, PASTA_BACKUPS / f"carteira_{carimbo}.csv")
        for antigo in sorted(PASTA_BACKUPS.glob("carteira_*.csv"))[:-MAX_BACKUPS]:
            antigo.unlink()
    out = df.sort_values(["data", "tipo"], kind="stable").copy()
    out["data"] = out["data"].dt.strftime("%Y-%m-%d")
    out["quantidade"] = out["quantidade"].apply(
        lambda x: int(x) if float(x).is_integer() else x
    )
    tmp = ARQ_CARTEIRA.with_suffix(".tmp")
    out[COLUNAS].to_csv(tmp, index=False)
    tmp.replace(ARQ_CARTEIRA)


def validar(df):
    """Devolve texto de erro, ou None se a lista de operações é coerente."""
    if df.empty:
        return None
    if not df["tipo"].isin(["compra", "venda"]).all():
        return "Tipo de operação inválido (use compra ou venda)."
    if (df["quantidade"] <= 0).any() or (df["preco"] <= 0).any():
        return "Quantidade e preço precisam ser maiores que zero."
    if (df["taxas"] < 0).any():
        return "Taxas não podem ser negativas."
    qtd = {}
    for r in df.sort_values(["data", "tipo"], kind="stable").itertuples():
        atual = qtd.get(r.ticker, 0.0)
        atual += r.quantidade if r.tipo == "compra" else -r.quantidade
        if atual < -1e-9:
            return (
                f"A venda de {r.ticker} em {r.data:%d/%m/%Y} é maior do que "
                f"a quantidade que você tinha nessa data."
            )
        qtd[r.ticker] = atual
    return None


def calcular_posicoes(df):
    """Preço médio ponderado. Devolve (posições, resultado realizado)."""
    pos, realizado = {}, {}
    for r in df.sort_values(["data", "tipo"], kind="stable").itertuples():
        p = pos.setdefault(r.ticker, {"qtd": 0.0, "custo": 0.0})
        if r.tipo == "compra":
            p["qtd"] += r.quantidade
            p["custo"] += r.quantidade * r.preco + r.taxas
        else:
            pm = p["custo"] / p["qtd"] if p["qtd"] else 0.0
            realizado[r.ticker] = (
                realizado.get(r.ticker, 0.0)
                + r.quantidade * r.preco - r.taxas - r.quantidade * pm
            )
            p["custo"] -= r.quantidade * pm
            p["qtd"] -= r.quantidade
            if p["qtd"] <= 1e-9:
                p["qtd"], p["custo"] = 0.0, 0.0
    return pos, realizado


# ------------------------------ DADOS DE MERCADO -------------------------


@st.cache_data(ttl=600, show_spinner=False)
def historico(simbolo, inicio):
    """Fechamentos diários (sem ajuste por proventos) desde 'inicio'."""
    try:
        h = yf.Ticker(simbolo).history(start=inicio, auto_adjust=False)
        s = h["Close"].dropna()
        if s.empty:
            return pd.Series(dtype=float)
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        s.index = s.index.normalize()
        return s[~s.index.duplicated(keep="last")]
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=60, show_spinner=False)
def cotacao(simbolo):
    """(preço atual, fechamento anterior) ou None."""
    try:
        fi = yf.Ticker(simbolo).fast_info
        p, a = float(fi["last_price"]), float(fi["previous_close"])
        return (p, a) if p > 0 and a > 0 else None
    except Exception:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def dividendos(ticker):
    """Proventos por ação (série indexada pela data ex)."""
    try:
        d = yf.Ticker(simb(ticker)).dividends.copy()
        if len(d) == 0:
            return pd.Series(dtype=float)
        if d.index.tz is not None:
            d.index = d.index.tz_localize(None)
        d.index = d.index.normalize()
        return d
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=21600, show_spinner=False)
def fundamentos(ticker):
    out = {"pl": None, "pvp": None, "prov12": None}
    try:
        info = yf.Ticker(simb(ticker)).info
        for chave, campo in (("pl", "trailingPE"), ("pvp", "priceToBook")):
            v = info.get(campo)
            if isinstance(v, (int, float)) and v > 0:
                out[chave] = float(v)
    except Exception:
        pass
    d = dividendos(ticker)
    if len(d):
        corte = pd.Timestamp.now().normalize() - pd.Timedelta(days=365)
        out["prov12"] = float(d[d.index >= corte].sum())
    return out


def preco_atual(ticker):
    cot = cotacao(simb(ticker))
    if cot:
        return cot[0]
    inicio = (dt.datetime.now(TZ) - dt.timedelta(days=15)).strftime("%Y-%m-%d")
    h = historico(simb(ticker), inicio)
    return float(h.iloc[-1]) if len(h) else None


# ------------------------------ CÁLCULOS DA CARTEIRA ---------------------


def evolucao_patrimonio(ops):
    """Patrimônio x aportes líquidos x Ibovespa com o mesmo fluxo de caixa."""
    inicio = ops["data"].min()
    busca = (inicio - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    ibov = historico(INDICE[0], busca)
    if ibov.empty:
        return None
    datas = ibov.index[ibov.index >= inicio]
    if len(datas) == 0:
        return None
    calendario = pd.date_range(inicio, datas[-1], freq="D")

    valor = pd.Series(0.0, index=datas)
    for t, g in ops.groupby("ticker"):
        delta = (
            pd.Series(np.where(g["tipo"] == "compra", g["quantidade"], -g["quantidade"]),
                      index=g["data"].values)
            .groupby(level=0).sum()
        )
        qtd = delta.reindex(calendario, fill_value=0).cumsum().reindex(datas)
        precos = historico(simb(t), busca)
        if precos.empty:
            continue
        precos = precos.reindex(precos.index.union(datas)).ffill().reindex(datas)
        valor = valor.add((qtd * precos).fillna(0.0), fill_value=0.0)

    caixa = np.where(
        ops["tipo"] == "compra",
        ops["quantidade"] * ops["preco"] + ops["taxas"],
        -(ops["quantidade"] * ops["preco"] - ops["taxas"]),
    )
    fluxo = pd.Series(caixa, index=ops["data"].values).groupby(level=0).sum()
    aportes = fluxo.reindex(calendario, fill_value=0).cumsum().reindex(datas)

    ibov_ff = ibov.reindex(ibov.index.union(calendario)).ffill()
    unidades_op = (fluxo / ibov_ff.reindex(fluxo.index)).fillna(0.0)
    unidades = unidades_op.reindex(calendario, fill_value=0).cumsum().reindex(datas)

    res = pd.DataFrame({"Patrimônio": valor, "Aportes líquidos": aportes})
    if not (unidades < -1e-9).any():
        res[f"{INDICE[1]} (mesmo fluxo)"] = unidades * ibov.reindex(datas)
    return res


def proventos_estimados(ops):
    """Proventos por ação x quantidade que você tinha na véspera da data ex."""
    por_ativo = {}
    for t, g in ops.groupby("ticker"):
        d = dividendos(t)
        if d.empty:
            continue
        delta = pd.Series(
            np.where(g["tipo"] == "compra", g["quantidade"], -g["quantidade"]),
            index=g["data"].values,
        ).groupby(level=0).sum()
        total = 0.0
        for dia, valor in d.items():
            q = delta[delta.index < dia].sum()
            if q > 0:
                total += q * float(valor)
        por_ativo[t] = total
    return sum(por_ativo.values()), por_ativo


# ------------------------------ INTERFACE --------------------------------


def estilo_figura(fig):
    fig.update_layout(
        hovermode="x unified",
        legend_orientation="h",
        legend_y=-0.2,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


def aba_visao_geral():
    hoje = dt.datetime.now(TZ)
    inicio = (hoje - dt.timedelta(days=400)).strftime("%Y-%m-%d")
    itens = [(t, simb(t)) for t in ATIVOS] + [(INDICE[1], INDICE[0])]

    cols = st.columns(len(itens))
    for col, (nome, s) in zip(cols, itens):
        cot = cotacao(s)
        if cot is None:
            col.metric(nome, "n/d")
            continue
        p, a = cot
        texto = (f"{p:,.0f}".replace(",", ".") if s.startswith("^") else brl(p))
        col.metric(nome, texto, f"{(p / a - 1) * 100:+.2f}%")

    st.subheader("Variação por período")
    periodos = {"24h": None, "7 dias": 7, "1 mês": 30, "3 meses": 90, "1 ano": 365}
    linhas = []
    for nome, s in itens:
        serie = historico(s, inicio)
        linha = {"Ativo": nome}
        for rotulo, dias in periodos.items():
            linha[rotulo] = pct(variacao(serie, dias) if len(serie) else None)
        linhas.append(linha)
    st.dataframe(pd.DataFrame(linhas), hide_index=True)
    st.caption(
        "\"24h\" é a variação do último pregão contra o anterior. Preços sem ajuste "
        "por proventos: em papéis que pagam muito dividendo, a data ex aparece como queda. "
        "Cotações podem ter atraso."
    )


def aba_graficos():
    hoje = dt.datetime.now(TZ)
    inicio = (hoje - dt.timedelta(days=800)).strftime("%Y-%m-%d")
    janelas = {"1 mês": 30, "3 meses": 90, "6 meses": 180, "1 ano": 365, "2 anos": 730}

    c1, c2 = st.columns([1, 3])
    janela = c1.selectbox("Período", list(janelas), index=1)
    escolhidos = c2.multiselect("Ativos", list(ATIVOS), default=list(ATIVOS))
    corte = pd.Timestamp(hoje.date()) - pd.Timedelta(days=janelas[janela])

    st.subheader("Comparação com o Ibovespa (base 100)")
    fig = go.Figure()
    for nome, s in [(t, simb(t)) for t in escolhidos] + [(INDICE[1], INDICE[0])]:
        serie = historico(s, inicio)
        serie = serie[serie.index >= corte]
        if len(serie) < 2:
            continue
        fig.add_trace(go.Scatter(
            x=serie.index, y=serie / serie.iloc[0] * 100, name=nome,
            line=dict(dash="dash", width=3) if s.startswith("^") else None,
        ))
    if fig.data:
        st.plotly_chart(estilo_figura(fig))
    else:
        st.warning("Sem dados para o período. Tente \"Atualizar dados\" na barra lateral.")

    st.subheader("Preço de um ativo")
    ativo = st.selectbox("Ativo", list(ATIVOS), key="ativo_unico")
    serie = historico(simb(ativo), inicio)
    serie = serie[serie.index >= corte]
    if len(serie) >= 2:
        f2 = px.line(x=serie.index, y=serie.values, labels={"x": "", "y": "Fechamento (R$)"})
        st.plotly_chart(estilo_figura(f2))


def formulario_operacao(ops):
    st.subheader("Registrar operação")
    hoje = dt.datetime.now(TZ).date()
    with st.form("nova_operacao", clear_on_submit=True):
        c = st.columns(6)
        data = c[0].date_input("Data", value=hoje, max_value=hoje, format="DD/MM/YYYY")
        ticker = c[1].selectbox("Ativo", list(ATIVOS))
        tipo = c[2].radio("Tipo", ["Compra", "Venda"], horizontal=True)
        qtd = c[3].number_input("Quantidade", min_value=1, step=1, value=1)
        preco = c[4].number_input(
            "Preço por ação (R$)", min_value=0.01, step=0.01, format="%.2f", value=1.00
        )
        taxas = c[5].number_input(
            "Taxas (R$, opcional)", min_value=0.0, step=0.01, format="%.2f", value=0.0
        )
        enviado = st.form_submit_button("Salvar operação")

    if enviado:
        nova = pd.DataFrame([{
            "data": pd.Timestamp(data), "ticker": ticker, "tipo": tipo.lower(),
            "quantidade": float(qtd), "preco": round(float(preco), 2),
            "taxas": round(float(taxas), 2),
        }])
        candidato = pd.concat([ops, nova], ignore_index=True)
        erro = validar(candidato)
        if erro:
            st.error(erro)
        else:
            salvar_carteira(candidato)
            st.session_state["msg"] = (
                f"{tipo} de {int(qtd)} {ticker} a {brl(preco)} salva."
            )
            st.rerun()


def tabela_operacoes(ops):
    st.subheader("Operações registradas")
    ver = ops.copy()
    ver["data"] = ver["data"].dt.strftime("%d/%m/%Y")
    ver["quantidade"] = ver["quantidade"].map(lambda x: f"{x:g}")
    ver["preco"] = ver["preco"].map(brl)
    ver["taxas"] = ver["taxas"].map(brl)
    ver.columns = ["Data", "Ativo", "Tipo", "Quantidade", "Preço", "Taxas"]
    st.dataframe(ver)

    with st.expander("Corrigir ou apagar uma operação"):
        st.caption(
            "Para corrigir um erro: apague a operação errada e registre a certa. "
            "Uma cópia de segurança do arquivo é feita antes de cada alteração "
            f"(pasta {PASTA_BACKUPS.name})."
        )
        ids = st.multiselect(
            "Operações a apagar (número da linha)", list(ops.index),
            format_func=lambda i: (
                f"{i}: {ops.loc[i, 'data']:%d/%m/%Y} {ops.loc[i, 'tipo']} "
                f"{ops.loc[i, 'quantidade']:g} {ops.loc[i, 'ticker']}"
            ),
        )
        confirma = st.checkbox("Confirmo que quero apagar as operações selecionadas")
        if st.button("Apagar selecionadas", disabled=not (ids and confirma)):
            restante = ops.drop(index=ids).reset_index(drop=True)
            erro = validar(restante)
            if erro:
                st.error(f"Não é possível apagar: {erro}")
            else:
                salvar_carteira(restante)
                st.session_state["msg"] = f"{len(ids)} operação(ões) apagada(s)."
                st.rerun()


def aba_carteira():
    if "msg" in st.session_state:
        st.success(st.session_state.pop("msg"))

    ops = carregar_carteira()
    formulario_operacao(ops)

    if ops.empty:
        st.info("Nenhuma operação registrada ainda. Use o formulário acima.")
        return

    pos, realizado = calcular_posicoes(ops)
    linhas = []
    for t, p in pos.items():
        if p["qtd"] <= 0:
            continue
        atual = preco_atual(t)
        valor = p["qtd"] * atual if atual else None
        res = valor - p["custo"] if valor is not None else None
        linhas.append({
            "Ativo": t, "qtd": p["qtd"], "pm": p["custo"] / p["qtd"],
            "atual": atual, "custo": p["custo"], "valor": valor, "res": res,
            "res_pct": (res / p["custo"] * 100) if res is not None and p["custo"] else None,
        })
    df = pd.DataFrame(linhas)

    st.subheader("Resumo")
    prov_total, _ = proventos_estimados(ops)
    realizado_total = sum(realizado.values())
    if not df.empty:
        valor_total = df["valor"].sum(min_count=1)
        custo_total = df["custo"].sum()
        res_total = valor_total - custo_total if pd.notna(valor_total) else None
        m = st.columns(5)
        m[0].metric("Patrimônio em ações", brl(valor_total))
        m[1].metric("Custo da posição", brl(custo_total))
        m[2].metric(
            "Resultado não realizado", brl(res_total),
            pct(res_total / custo_total * 100) if res_total is not None and custo_total else None,
        )
        m[3].metric("Resultado realizado (vendas)", brl(realizado_total))
        m[4].metric("Proventos estimados", brl(prov_total))
    else:
        st.info("Você não tem posição aberta (tudo vendido).")
        st.metric("Resultado realizado (vendas)", brl(realizado_total))

    if not df.empty:
        total = df["valor"].sum(min_count=1)
        mostrar = pd.DataFrame({
            "Ativo": df["Ativo"],
            "Quantidade": df["qtd"].map(lambda x: f"{x:g}"),
            "Preço médio": df["pm"].map(brl),
            "Preço atual": df["atual"].map(brl),
            "Custo": df["custo"].map(brl),
            "Valor atual": df["valor"].map(brl),
            "Resultado": df["res"].map(brl),
            "Resultado %": df["res_pct"].map(pct),
            "Peso": (df["valor"] / total * 100).map(lambda v: pct(v, sinal=False)),
        })
        st.dataframe(mostrar, hide_index=True)
        st.caption(
            "Preço médio inclui taxas de compra. Proventos estimados = provento por ação "
            "x quantidade que você tinha antes da data ex, bruto (sem desconto de imposto "
            "sobre JCP) e conforme a fonte de dados; confirme no extrato da corretora ou no "
            "informe de rendimentos."
        )

    c1, c2 = st.columns(2)
    if not df.empty and df["valor"].notna().any():
        pizza = px.pie(df.dropna(subset=["valor"]), names="Ativo", values="valor", hole=0.4)
        pizza.update_layout(margin=dict(l=10, r=10, t=30, b=10), title="Distribuição por valor")
        c1.plotly_chart(pizza)

    delta = ops.assign(
        d=np.where(ops["tipo"] == "compra", ops["quantidade"], -ops["quantidade"])
    )
    qtd_tempo = delta.groupby(["data", "ticker"])["d"].sum().unstack(fill_value=0).cumsum()
    fq = px.line(qtd_tempo, line_shape="hv", labels={"value": "Ações", "data": "", "ticker": ""})
    fq.update_layout(title="Quantidade de ações ao longo do tempo", margin=dict(l=10, r=10, t=40, b=10))
    c2.plotly_chart(fq)

    st.subheader("Evolução do patrimônio")
    evo = evolucao_patrimonio(ops)
    if evo is None:
        st.warning("Não foi possível montar a evolução (sem dados de mercado).")
    else:
        fe = go.Figure()
        for col in evo.columns:
            fe.add_trace(go.Scatter(x=evo.index, y=evo[col], name=col))
        st.plotly_chart(estilo_figura(fe))
        st.caption(
            f"\"{INDICE[1]} (mesmo fluxo)\" simula comprar e vender o índice nos mesmos dias "
            "e valores das suas operações, para comparar o seu resultado com o do mercado. "
            "É uma aproximação: ignora custos e proventos."
        )

    tabela_operacoes(ops)


def aba_fundamentalistas():
    linhas = []
    for t in ATIVOS:
        f = fundamentos(t)
        p = preco_atual(t)
        dy = (f["prov12"] / p * 100) if f["prov12"] is not None and p else None
        linhas.append({
            "Ativo": t,
            "Preço": brl(p),
            "P/L": "n/d" if f["pl"] is None else f"{f['pl']:.1f}",
            "P/VP": "n/d" if f["pvp"] is None else f"{f['pvp']:.2f}",
            "Proventos 12m (R$/ação)": brl(f["prov12"]),
            "Dividend yield 12m": pct(dy, sinal=False),
        })
    st.dataframe(pd.DataFrame(linhas), hide_index=True)
    st.caption(
        "Dividend yield = proventos pagos nos últimos 12 meses (conforme a fonte) dividido "
        "pelo preço atual. Pode não incluir todos os juros sobre capital próprio. P/L e P/VP "
        "vêm da fonte de dados e podem estar ausentes (n/d) ou desatualizados. Confira em "
        "fonte oficial (RI das empresas, B3) antes de usar qualquer número."
    )


def aba_alertas():
    if not ARQ_ALERTAS.exists():
        st.info(
            "Nenhum alerta registrado ainda. Eles aparecem aqui quando o "
            "monitor_acoes.py estiver rodando e enviar alertas."
        )
        return
    try:
        al = pd.read_csv(ARQ_ALERTAS)
        al["data_hora"] = pd.to_datetime(al["data_hora"])
    except Exception as e:
        st.error(f"Não consegui ler alertas.csv: {e}")
        return
    if al.empty:
        st.info("O histórico de alertas está vazio.")
        return

    filtro = st.multiselect("Ativos", sorted(al["ticker"].unique()),
                            default=sorted(al["ticker"].unique()))
    al = al[al["ticker"].isin(filtro)].sort_values("data_hora", ascending=False)

    m = st.columns(3)
    m[0].metric("Alertas", len(al))
    m[1].metric("Altas", int((al["sentido"] == "ALTA").sum()))
    m[2].metric("Quedas", int((al["sentido"] == "QUEDA").sum()))

    ver = al.copy()
    ver["data_hora"] = ver["data_hora"].dt.strftime("%d/%m/%Y %H:%M")
    ver.columns = ["Data/hora", "Ativo", "Sentido", "Variação %", "Preço",
                   "Fech. anterior", "WhatsApp enviado"]
    st.dataframe(ver, hide_index=True)

    cont = al.groupby(["ticker", "sentido"]).size().reset_index(name="alertas")
    if not cont.empty:
        st.plotly_chart(px.bar(cont, x="ticker", y="alertas", color="sentido",
                               labels={"ticker": "", "alertas": "Alertas"}))


def main():
    st.set_page_config(page_title="Painel de ações", page_icon="📈", layout="wide")
    st.title("Painel de ações")

    with st.sidebar:
        st.header("Controles")
        if st.button("Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.caption(
            f"Aberto em {dt.datetime.now(TZ):%d/%m/%Y %H:%M}. Dados da yfinance "
            "(fonte não oficial, possível atraso). Informativo; não é recomendação "
            "de investimento."
        )

    abas = st.tabs(["Visão geral", "Gráficos", "Carteira", "Fundamentalistas", "Alertas"])
    with abas[0]:
        aba_visao_geral()
    with abas[1]:
        aba_graficos()
    with abas[2]:
        aba_carteira()
    with abas[3]:
        aba_fundamentalistas()
    with abas[4]:
        aba_alertas()


if __name__ == "__main__":
    main()
