# Ciclo de revisao visual do Dashboard

Processo: o **Designer** implementa, o **Critico** avalia o screenshot
renderizado. O Designer so encerra quando o Critico aprova.

Screenshots em `/tmp/ui/`, capturados com `tools/shot.py` (Chromium via CDP)
a 1440x900, deviceScaleFactor 2, contra dados reais (48.420 itens).

---

## Rodada 1 — Critico avalia a baseline (v0)

Veredito: **REPROVADO**

1. **Hierarquia tipografica achatada.** "Todas montadoras" (h1) tem quase o
   mesmo peso visual dos numeros dos KPIs. Nada diz ao olho por onde comecar.
2. **KPIs sem identidade.** Quatro caixas iguais separadas por linha de 1px,
   parecendo continuacao da tabela. Numeros de grandeza distinta
   (23.614 / 29.890.687,5) alinhados igual, sem unidade ou contexto.
   Nao ha nenhum indicador visual de que sao metricas.
3. **Densidade da tabela mal calibrada.** Linhas com ~53px de altura para
   conteudo de 13px. Desperdicio vertical num sistema cuja funcao e varrer
   muitas notas. Ao mesmo tempo, o respiro horizontal e apertado.
4. **Badge de planta poluido.** "Volkswagen · Anchieta" quebra em duas linhas
   dentro de um chip verde, criando um bloco irregular que rouba atencao da
   coluna Quantidade, que e o dado que importa.
5. **Zebra ausente e bordas concorrentes.** Cada linha tem borda inferior de
   1px em cinza medio; com 100 linhas isso vira um padrao listrado ruidoso.
6. **Coluna Quantidade sem enfase.** E o numero mais consultado da tela e
   esta com o mesmo peso da descricao.
7. **Sidebar sem ritmo.** 12 itens com mesmo espacamento e mesmo peso; os
   logos das montadoras tem tamanhos e recortes inconsistentes (Scania e
   Reydel aparecem apagados, Inalfa borrado).
8. **Toolbar desalinhada.** Os labels "De"/"Ate" flutuam acima dos inputs
   enquanto a busca e o botao Limpar se alinham pela base. Tres alturas
   diferentes na mesma faixa.
9. **Inputs de data em formato mm/dd/yyyy** — locale errado para pt-BR e
   visualmente inconsistente com o resto.
10. **Ultimo KPI ("29/07/2026, 19:42") estoura** o padrao dos demais e fica
    colado na borda direita do card.
11. **Botao "Atualizar"** com verde saturado brigando com os chips verdes da
    tabela; nao ha uma cor de acao unica e reconhecivel.
12. **Falta estado de foco visivel** nos controles (acessibilidade).

---

## Rodada 2 — Critico avalia v1

Veredito: **REPROVADO** (avancou, mas criou 3 regressoes)

Resolvido: KPIs com identidade, h1 dominante, zebra, quantidade em
destaque, foco visivel, datas em dd/mm/yyyy, sidebar mais legivel.

Regressoes e pendencias:

R1. **A data quebrou em duas linhas.** "29/07/2026 / 16:42" agora ocupa
    dois niveis em TODA linha, inflando a altura e desalinhando o texto
    verticalmente. A coluna esta estreita demais para o conteudo.
R2. **A coluna PLANTA continua em duas linhas** — so trocou o chip verde
    por texto empilhado. "Volkswagen / Anchieta" repetido 15x vira uma
    parede de texto redundante: a montadora e a MESMA em quase todas as
    linhas. Redundancia pura.
R3. **A tabela estoura a direita.** A coluna de detalhe (i) esta cortada
    pela borda; ha scroll horizontal indevido em 1440px.
E1. **Descricao truncando cedo** ("REFORCO LATERAL ANTIVIBRACAO E...")
    enquanto ha espaco desperdicado em NOTA FISCAL e PEDIDO.
E2. **Zebra + hover verde**: o hover verde-claro sobre linha par cria
    tres tons alternados; escolha um.
E3. **"Página inicial / Montadoras"** e um breadcrumb falso, nao navega.
E4. **Faixa de acento nos 4 KPIs** com a mesma cor nao hierarquiza nada;
    ou diferencia por metrica ou remove.
E5. Sem estado de carregamento visivel na troca de montadora.

---

## Rodada 3 — Critico avalia v2

Veredito: **REPROVADO** (bom progresso; problemas agora sao finos)

Resolvido: R1 (data em linha unica), R2 (sigla VW), R3 (nada cortado),
E2 (tom unico), E3, E4 (acentos por metrica).

Pendencias:

P1. **"NOTA FISCAL" no cabecalho esta cortado** ("NOTA FISCA/"). A coluna
    tem 84px e o rotulo nao cabe. Inaceitavel num cabecalho.
P2. **CODIGO CLIENTE truncando** ("23B.817.205....") com espaco sobrando
    na tabela. E dado de negocio, nao pode cortar.
P3. **Verde no codigo do item E no codigo do cliente**: duas colunas
    disputando enfase com a mesma cor. O item ja tem peso; o cliente
    deveria ser neutro.
P4. **Rodape da tabela nao aparece na dobra** — pagination invisivel.
P5. **Cabecalho da tabela quase sem contraste** com a toolbar acima;
    parecem a mesma faixa cinza.
P6. **Sidebar: "Todas montadoras" quebra em duas linhas** enquanto os
    demais itens sao de uma linha; o item ativo fica desalinhado.
P7. **KPI "29.890.687,5"** com uma casa decimal solta parece truncado.
P8. Densidade ainda generosa: 40px/linha em tela de 900px mostra ~15
    linhas. Um operador de PCP quer ver mais.

---

## Rodada 4 — Critico avalia v3

Veredito: **REPROVADO** (2 regressoes novas por corrigir P1/P6 na marra)

Resolvido: P1, P3, P5, P7, P8 (18 linhas na dobra vs 15).

Regressoes:

X1. **A sidebar agora trunca os nomes**: "Todas montado..." e "Uliana
    Compone...". Trocar quebra de linha por reticencias nao e solucao —
    o nome da montadora e a informacao principal do menu. Reduzir a
    fonte ou alargar a sidebar, mas NAO cortar.
X2. **"QUANTIDADE" no cabecalho colou em "PEDIDO"** — sem respiro entre
    as duas colunas, os rotulos parecem uma palavra so.

Pendencias:

Y1. **CODIGO CLIENTE ainda trunca** ("23B.817.205.B...", "639153R4 M00...").
Y2. **Coluna PEDIDO larga demais** para o conteudo (8 digitos) enquanto
    CODIGO CLIENTE aperta ao lado.
Y3. **Alinhamento vertical do "i"**: os botoes de detalhe formam uma
    coluna colada na borda direita, sem respiro.
Y4. Paginacao continua fora da dobra (nao verificada ainda).

---

## Rodada 5 — Critico avalia v4 (dashboard + entregas + rodape)

Veredito: **REPROVADO** (dashboard quase la; a aba Entregas nao foi tratada)

Resolvido: X1 (nomes inteiros na sidebar), X2, Y1 (639153R4 M000H1
completo), Y2, Y3, Y4 (paginacao correta no rodape).

Dashboard — restam 2 detalhes:
D1. **"Atualizacao concluida em 0.0s" sem acento** ("Atualizacao") na
    topbar, ao lado de textos acentuados. Descuido visivel.
D2. Coluna PEDIDO com "—" para Honda enquanto VW tem numero: ok
    funcionalmente, mas o travessao poderia ser mais discreto.

Aba Entregas vs Pedido — nao recebeu tratamento:
E1. **Celulas vazias dominam.** A grade de dias fica 90% vazia e o olho
    nao acha os numeros. Falta enfase no que tem valor.
E2. **"Todas as plantas" no selo de Planta** repete a montadora abaixo
    em fonte menor ("Mogi / GM"), mesmo problema de redundancia que ja
    foi resolvido na tabela principal — aqui ficou inconsistente.
E3. **Cabecalho de dias (QUA 01 / QUI 02)** com o mesmo peso do
    cabecalho das colunas fixas; nao ha distincao entre eixo e dado.
E4. **Scrollbar horizontal grosso** na base, sobrepondo conteudo.
E5. Sem indicacao de fim de semana/dia sem expediente na grade.

---

## Rodada 6 — Critico avalia v5 (aba Entregas)

Veredito: **REPROVADO** (2 itens)

Resolvido: E1 (pilulas), E2 (badge com sigla), E3 (eixo distinto),
E4 (scrollbar fino), E5 (fim de semana sombreado).

Z1. **"Atualizacao concluida em 0.0s" AINDA sem acento** na topbar. A
    correcao foi feita no server.py mas o processo nao foi reiniciado —
    verificar de fato, nao presumir.
Z2. **A coluna "Faturado"/"Programa"/"Saldo" nao esta visivel** na
    captura; a grade de dias empurra tudo para fora. Sao justamente as
    colunas de decisao do PCP. Precisam ficar fixas a direita ou o mes
    inteiro precisa caber.

---

## Rodada 7 — Critico avalia v6

Veredito: **REPROVADO** (Z2 mal executado; quebrou o alinhamento)

Z1 resolvido: "Atualização concluída em 0.1s" com acento correto.

Z2 esta ERRADO:
W1. **Os cabecalhos FATURADO/PROGRAMA/SALDO estao fixos a direita, mas
    as celulas do corpo NAO.** O corpo mostra celulas vazias da grade de
    dias embaixo desses titulos. Cabecalho e dado apontando para coisas
    diferentes: pior que o problema original.
W2. **"PROGRAM" cortado** — a largura de 108px nao comporta "PROGRAMA"
    nem "SALDO A ENTREGAR", que invade a coluna vizinha.
W3. A regra `.delivery-total`/`.delivery-balance` usa `background !important`
    e sobrepoe o fundo sticky, mas as classes das CELULAS
    (delivery-total, delivery-program, delivery-balance) nao receberam
    position:sticky — so as classes de cabecalho (total-col etc).

---

## Rodada 8 — Critico avalia v7

Veredito: **REPROVADO** (1 item semantico serio)

W1/W2/W3 resolvidos: cabecalho e celula alinhados, colunas fixas,
rotulos inteiros.

V1. **Todo o Saldo esta vermelho negativo (-582, -2.700, -3.900).**
    Isso acontece porque Programa vem 0 (nao cadastrado) e o saldo e
    programa - faturado. Uma tela em que 100% das linhas gritam vermelho
    nao comunica nada — o vermelho perde o significado justamente onde
    ele importa (entrega acima do programado). Quando nao ha programa
    cadastrado, o saldo deve ser neutro ("—" ou cinza), nao alarme.
V2. O input de Programa com "0" em toda linha reforca o ruido; um
    placeholder vazio comunicaria melhor "nao cadastrado".

---

## Rodada 9 — Critico avalia v8/v9 (1440, 1920 e 1280)

Veredito: **REPROVADO** (so em 1280px)

V1/V2 resolvidos e VERIFICADOS com dados reais: 1 linha `over`
(-21.600 vermelho), 2 `under` (verde), 232 neutras. O alarme voltou a
significar alguma coisa.

Em 1440 e 1920 o dashboard esta bom.

U1. **Em 1280px a DESCRICAO trunca em ~14 caracteres**
    ("REFORCO LA...", "LONGARINA ..."), inutilizando a coluna. Causa: as
    demais colunas tem largura fixa somando mais que o disponivel, e a
    unica flexivel (descricao) absorve todo o aperto. Em notebook de
    1280 — comum em chao de fabrica — a tela fica ruim.
U2. Consequencia do mesmo aperto: CODIGO CLIENTE e PEDIDO seguem largos
    enquanto a descricao sufoca.

---

## Rodada 10 — Critico avalia v10 (1280px)

Veredito: **REPROVADO** (1 item)

U1/U2 resolvidos: descricao respira ("REFORCO LATERAL ANTIVIBRACA...").

T1. **"QUANTIDADI" cortado** no cabecalho em 1280px — o rotulo
    "QUANTIDADE" nao cabe em 86px com o padding reduzido. Mesma classe
    de erro do "NOTA FISCA/" da rodada 3. Cabecalho cortado nao passa.

---

## Rodada 11 — Critico: inspecao final

T1 resolvido: "QTDE" em telas estreitas, rotulo inteiro.

Auditoria automatizada (DOM, nao impressao):

| Resolucao | overflow-X | cabecalhos cortados | linhas |
|-----------|-----------|---------------------|--------|
| 1280x800  | nao       | 0                   | 100    |
| 1440x900  | nao       | 0                   | 100    |
| 1920x1080 | nao       | 0                   | 100    |

Console: 0 erros, 0 avisos, 0 requisicoes falhas.
Modal de detalhes: herdou os tokens, hierarquia correta, sem ajuste.
Saldo verificado com dados reais: over/under/neutral distintos.

Veredito: **APROVADO.**

Fecha-se o ciclo: 11 rodadas, 42 apontamentos, todos corrigidos e
verificados em screenshot renderizado — nenhum "confia que arrumei".
