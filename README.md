# Monitor de ações da B3

Projeto pessoal para acompanhar ações brasileiras. Ele faz três coisas:

- **Alerta no WhatsApp** quando uma ação sobe ou cai além do limite que você definir (`monitor_acoes.py`).
- **Relatório de variação** do último pregão, 7 dias, 1 mês e 3 meses (`relatorio_acoes.py`).
- **Painel web** com gráficos, comparação com o Ibovespa, indicadores fundamentalistas, histórico de alertas e a sua carteira (`painel.py`).

> **Aviso:** este projeto é informativo e educacional. Nada aqui é recomendação de compra, venda ou manutenção de ativos, e eu não sou consultor de investimentos. Os dados vêm de fontes não oficiais, podem ter atraso ou erro, e devem ser conferidos em fonte oficial ou na sua corretora antes de qualquer decisão.

---

## Cada pessoa usa a própria cópia

Esta versão foi feita para **uma pessoa por instalação**: uma lista de ações, um número de WhatsApp e uma carteira. Não há login nem separação de usuários. Se outra pessoa quiser usar, ela copia a pasta e segue este guia com os dados dela. A carteira de cada um fica só no `carteira.csv` da própria cópia.

---

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `config.py` | **Onde você escolhe as ações** e o limite de alerta de cada uma |
| `monitor_acoes.py` | Fica ligado durante o pregão e envia os alertas por WhatsApp |
| `relatorio_acoes.py` | Gera o relatório de variação (na tela ou no WhatsApp) |
| `painel.py` | Painel web (Streamlit) |
| `requirements.txt` | Lista das bibliotecas necessárias |
| `.env.example` | Modelo para guardar o número e a chave do WhatsApp |
| `.gitignore` | Impede que dados pessoais sejam enviados ao repositório |

Criados automaticamente quando você usa o projeto (não vão para o repositório):

| Arquivo | Conteúdo |
|---|---|
| `alertas.csv` | Histórico dos alertas enviados |
| `carteira.csv` | Suas compras e vendas |
| `backups/` | Cópias de segurança automáticas da carteira |

---

## 1. Instalação

Você precisa do **Python 3.9 ou mais novo**. No terminal, dentro da pasta do projeto:

```bash
pip install -r requirements.txt
```

> Em alguns sistemas o comando é `pip3` e `python3` em vez de `pip` e `python`. Use o que funcionar no seu.

Opcional, mas recomendado: crie um ambiente virtual antes, para não misturar com outros programas.

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

---

## 2. Escolher as ações que você quer acompanhar

Abra o `config.py` e edite o dicionário `ATIVOS`. Cada linha tem o **código da ação (sem `.SA`)** e o **degrau de variação, em %**, que dispara o alerta:

```python
ATIVOS = {
    "WEGE3": 3.0,
    "MGLU3": 5.0,
    "HGLG11": 1.5,
}
```

Como o degrau funciona: com `3.0`, você recebe um aviso quando a ação chegar a +3% ou -3% em relação ao fechamento anterior, outro em +6% ou -6%, e assim por diante. Ele não repete a mesma mensagem a cada consulta.

Dicas:

- **Ações, FIIs e ETFs** usam o mesmo formato (por exemplo `BOVA11`), desde que a fonte de dados tenha o código.
- **Ajuste o degrau ao papel.** Um fundo imobiliário oscila bem menos que uma ação de empresa pequena. Com degrau baixo demais, o alerta dispara o dia inteiro.
- **Confira se o código existe** antes de colocá-lo (troque `WEGE3` pelo seu):

  ```bash
  python -c "import yfinance as yf; print(yf.Ticker('WEGE3.SA').history(period='5d')['Close'])"
  ```

  Se vier vazio ou com erro, o código está errado ou a fonte não tem esse papel.
- **Depois de salvar o `config.py`**, reinicie o monitor e recarregue o painel. Todos os programas leem a lista do mesmo lugar.

Cuidados ao mudar a lista:

- Se você **remover** uma ação que já tem operações registradas, o formulário deixa de oferecê-la, mas as operações antigas continuam no `carteira.csv` e entram nos cálculos da carteira.
- Se uma empresa **mudar de código**, não renomeie só no `config.py`: ajuste também o `carteira.csv`, senão o histórico fica dividido em dois ativos.

O índice de comparação (Ibovespa) também fica no `config.py`, na variável `INDICE`.

---

## 3. Configurar o alerta por WhatsApp

O envio usa o **CallMeBot**, um serviço gratuito e **não oficial**, pensado para uso pessoal. Ele pode mudar as regras ou sair do ar. Se você precisar de algo mais estável, dá para trocar apenas a função `enviar_whatsapp` no `monitor_acoes.py` por outra opção (por exemplo, Twilio ou a API oficial da Meta).

**Passo 1.** Entre em [callmebot.com](https://www.callmebot.com), siga as instruções de WhatsApp para autorizar o serviço no seu número e anote a **chave (apikey)** que ele fornecer. Siga o que estiver no site no momento do cadastro, porque o procedimento pode mudar.

**Passo 2.** Defina duas variáveis com os seus dados:

- `WHATSAPP_PHONE`: seu número com código do país e DDD, só dígitos, sem `+` nem espaços. Exemplo: `5535999999999`.
- `CALLMEBOT_APIKEY`: a chave recebida no passo 1.

Os dados **não ficam dentro do código**. Escolha uma das formas:

**Windows (PowerShell), vale só para a janela aberta:**
```powershell
$env:WHATSAPP_PHONE="5535999999999"
$env:CALLMEBOT_APIKEY="sua_chave"
```

**Mac ou Linux, vale só para a janela aberta:**
```bash
export WHATSAPP_PHONE="5535999999999"
export CALLMEBOT_APIKEY="sua_chave"
```

**Usando um arquivo `.env`** (melhor para servidor ou Raspberry): copie o modelo e preencha.
```bash
cp .env.example .env
nano .env
chmod 600 .env
```
O programa **não lê o `.env` sozinho**. Quem o lê é o serviço `systemd` da seção 6, ou você pode carregá-lo no terminal (Mac/Linux):
```bash
set -a; source .env; set +a
```

**Passo 3. Teste:**
```bash
python monitor_acoes.py --test
```
Se chegar a mensagem "Teste do monitor de ações: funcionando." no seu WhatsApp, está tudo certo.

> **Nunca publique a chave** nem o arquivo `.env`. Quem tiver a chave consegue enviar mensagens para o seu número por esse serviço.

---

## 4. Como usar

**Monitor de alertas** (deixe rodando; consulta a cada 5 minutos, das 10h às 17h55, em dias úteis):
```bash
python monitor_acoes.py
```
O horário e o intervalo ficam no topo do `monitor_acoes.py`. O programa não conhece feriados da B3; nesses dias simplesmente não verá mudança de preço.

**Relatório de variação:**
```bash
python relatorio_acoes.py             # mostra na tela
python relatorio_acoes.py --enviar    # também manda o resumo no WhatsApp
```
O "24h" é a variação do último pregão contra o anterior, já que a bolsa não opera 24 horas. Os preços são **sem ajuste por proventos**: em papéis que pagam muito dividendo, o dia da data ex aparece como queda de preço.

**Painel web:**
```bash
streamlit run painel.py --server.address 0.0.0.0 --server.port 8501
```
Abra `http://IP-DO-SEU-COMPUTADOR:8501` no navegador, no próprio computador ou em outro aparelho **na mesma rede Wi-Fi**. No Raspberry ou Linux, o IP aparece com `hostname -I`.

> **O painel não tem senha.** Quem estiver na sua rede consegue ver a carteira e também registrar ou apagar operações. Não exponha a porta na internet.

O painel tem cinco abas: Visão geral, Gráficos, Carteira, Fundamentalistas e Alertas.

---

## 5. Carteira

Na aba **Carteira** há o formulário **Registrar operação**: data, ativo, compra ou venda, quantidade, preço por ação e taxas (opcional). A cada operação salva, o painel faz uma cópia de segurança do arquivo na pasta `backups/` (guarda as últimas 30).

- O programa **não se conecta à corretora nem à B3**. Você registra as operações manualmente.
- O preço médio é ponderado e inclui as taxas de compra.
- Para corrigir um erro, apague a operação errada (no expander "Corrigir ou apagar uma operação") e registre a certa.
- Os **proventos estimados** usam o provento por ação informado pela fonte vezes a quantidade que você tinha antes da data ex. São valores brutos, podem não incluir todo o JCP e **não substituem o extrato da corretora nem o informe de rendimentos**.

Se preferir, o `carteira.csv` pode ser editado à mão, com estas colunas:

```csv
data,ticker,tipo,quantidade,preco,taxas
2026-07-06,PETR4,compra,100,30.00,5.00
2026-09-01,PETR4,venda,50,45.00,2.00
```
(`tipo` é `compra` ou `venda`; a data é `AAAA-MM-DD`.)

---

## 6. Deixar ligado 24 horas (Raspberry Pi ou servidor Linux)

Qualquer Raspberry Pi 3B+, Pi 4 ou mais recente serve para o monitor. O painel usa mais memória, então prefira um Pi 4 com 2 GB ou mais. Use um cartão microSD de boa qualidade e, se possível, cabo de rede.

Com o projeto em `/home/usuario/monitor` e o ambiente virtual em `venv`, crie o serviço:

```bash
sudo nano /etc/systemd/system/monitor-acoes.service
```

```ini
[Unit]
Description=Monitor de acoes B3
After=network-online.target
Wants=network-online.target

[Service]
User=usuario
WorkingDirectory=/home/usuario/monitor
EnvironmentFile=/home/usuario/monitor/.env
ExecStart=/home/usuario/monitor/venv/bin/python monitor_acoes.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Troque `usuario` pelo seu usuário e ative:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now monitor-acoes
```

Comandos úteis:

```bash
sudo systemctl status monitor-acoes     # está rodando?
journalctl -u monitor-acoes -f          # acompanhar o que ele faz
sudo systemctl restart monitor-acoes    # depois de editar config.py
```

Para o painel também ficar sempre ligado, crie um segundo serviço do mesmo jeito, trocando a linha `ExecStart` por:

```
ExecStart=/home/usuario/monitor/venv/bin/streamlit run painel.py --server.address 0.0.0.0 --server.port 8501
```

e dando outro nome ao arquivo (por exemplo `painel-acoes.service`).

Segurança básica em qualquer servidor: use login por chave SSH ou senha forte, mantenha o sistema atualizado (`sudo apt upgrade`) e nunca coloque a chave do WhatsApp dentro do código.

---

## 7. Problemas comuns

- **"Defina WHATSAPP_PHONE e CALLMEBOT_APIKEY"**: as variáveis não foram definidas na mesma janela do terminal em que você rodou o programa. Defina de novo (seção 3).
- **A mensagem de teste não chega**: confira o formato do número (só dígitos, com `55` e DDD) e refaça a autorização no site do CallMeBot.
- **`ModuleNotFoundError`**: rode o comando dentro da pasta do projeto e confirme que instalou o `requirements.txt` (e que o ambiente virtual está ativo).
- **Cotação vazia ou "n/d"**: o código da ação pode estar errado, ou a fonte de dados (`yfinance`) pode estar fora do ar ou ter atraso. Teste o código com o comando da seção 2 e use o botão "Atualizar dados" do painel.
- **Não chegam alertas**: o pregão pode estar fechado (o monitor só consulta de 10h a 17h55, em dias úteis), o degrau pode estar alto demais para o movimento do dia, ou o monitor pode não estar rodando.
- **O painel não abre no celular**: confirme que o celular está na mesma rede Wi-Fi, que o IP está certo, que o painel foi iniciado com `--server.address 0.0.0.0` e que o firewall do computador não bloqueia a porta 8501.
- **P/L ou P/VP aparecem como "n/d"**: a fonte não tem o dado para aquele papel. O painel não preenche número que não encontrou.

---

## 8. Limitações importantes

- **Dados com possível atraso** (em torno de 15 minutos) e vindos de uma fonte **não oficial**, que pode falhar ou mudar sem aviso. Não serve para operações que dependem de segundos.
- **CallMeBot também é não oficial** e voltado a uso pessoal.
- O monitor só funciona **enquanto estiver rodando**. Se o computador desligar ou a internet cair, você perde os alertas.
- O monitor não avisa quando ele mesmo falha. Confira o log de vez em quando.
- Indicadores e gráficos descrevem o que **já aconteceu**. Eles não indicam o que fazer.

Para decisões de investimento, converse com um profissional habilitado.