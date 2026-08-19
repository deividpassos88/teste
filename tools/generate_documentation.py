from pathlib import Path
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, HRFlowable, NextPageTemplate
)
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "Documentacao_Tecnica_e_Funcional_NFe_Monitor.pdf"
TMP = ROOT / "tmp" / "pdfs"
OUT.parent.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor("#17252B")
TEAL = colors.HexColor("#008C7A")
TEAL_DARK = colors.HexColor("#00695C")
MINT = colors.HexColor("#E8F4F1")
BLUE = colors.HexColor("#DDECF3")
INK = colors.HexColor("#172126")
MUTED = colors.HexColor("#5F6D73")
LINE = colors.HexColor("#CDD8DC")
LIGHT = colors.HexColor("#F4F7F8")
AMBER = colors.HexColor("#F4E7C6")
RED = colors.HexColor("#B83A3A")
WHITE = colors.white

font_regular = "Arial"
font_bold = "Arial-Bold"
arial = Path(r"C:\Windows\Fonts\arial.ttf")
arial_bold = Path(r"C:\Windows\Fonts\arialbd.ttf")
if arial.exists() and arial_bold.exists():
    pdfmetrics.registerFont(TTFont(font_regular, str(arial)))
    pdfmetrics.registerFont(TTFont(font_bold, str(arial_bold)))
else:
    font_regular, font_bold = "Helvetica", "Helvetica-Bold"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    "BodyLocal", fontName=font_regular, fontSize=9.2, leading=13.2,
    textColor=INK, spaceAfter=6
))
styles.add(ParagraphStyle(
    "SmallLocal", fontName=font_regular, fontSize=7.6, leading=10.5,
    textColor=MUTED
))
styles.add(ParagraphStyle(
    "H1Local", fontName=font_bold, fontSize=22, leading=26,
    textColor=NAVY, spaceAfter=10
))
styles.add(ParagraphStyle(
    "H2Local", fontName=font_bold, fontSize=14, leading=18,
    textColor=TEAL_DARK, spaceBefore=8, spaceAfter=7
))
styles.add(ParagraphStyle(
    "H3Local", fontName=font_bold, fontSize=10.5, leading=13,
    textColor=NAVY, spaceBefore=6, spaceAfter=4
))
styles.add(ParagraphStyle(
    "BulletLocal", fontName=font_regular, fontSize=8.8, leading=12.3,
    leftIndent=13, firstLineIndent=-7, bulletIndent=3, textColor=INK,
    spaceAfter=3
))
styles.add(ParagraphStyle(
    "CaptionLocal", fontName=font_regular, fontSize=7.5, leading=10,
    textColor=MUTED, alignment=TA_CENTER, spaceBefore=4
))
styles.add(ParagraphStyle(
    "CalloutLocal", fontName=font_regular, fontSize=9, leading=12.5,
    textColor=INK, leftIndent=8, rightIndent=8, spaceAfter=4
))


def P(text, style="BodyLocal"):
    return Paragraph(text, styles[style])


def bullet(text):
    return Paragraph(f"• {text}", styles["BulletLocal"])


def section(title, subtitle=None):
    out = [P(title, "H1Local"), HRFlowable(width="100%", thickness=1.2, color=TEAL)]
    if subtitle:
        out += [Spacer(1, 3 * mm), P(subtitle)]
    out.append(Spacer(1, 2 * mm))
    return out


def callout(title, text, color=MINT):
    data = [[P(title, "H3Local")], [P(text, "CalloutLocal")]]
    table = Table(data, colWidths=[170 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def data_table(rows, widths, header=True, font_size=7.7):
    cooked = []
    for r, row in enumerate(rows):
        cooked.append([
            cell if hasattr(cell, "wrap") else
            Paragraph(str(cell), ParagraphStyle(
                f"cell-{r}-{c}", fontName=font_bold if header and r == 0 else font_regular,
                fontSize=font_size, leading=font_size + 2, textColor=WHITE if header and r == 0 else INK
            ))
            for c, cell in enumerate(row)
        ])
    table = Table(cooked, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY if header else WHITE),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
    ]))
    return table


def screenshot(path, caption, width=170 * mm):
    img = Image(str(path))
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width
    img.drawHeight = width * ratio
    return KeepTogether([img, P(caption, "CaptionLocal")])


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        if self._pageNumber == 1:
            return
        w, _ = self._pagesize
        self.saveState()
        self.setStrokeColor(LINE)
        self.line(18 * mm, 13 * mm, w - 18 * mm, 13 * mm)
        self.setFont(font_regular, 7)
        self.setFillColor(MUTED)
        self.drawString(18 * mm, 8 * mm, "NF-e Monitor | Uliana Indústria Metalúrgica Ltda.")
        self.drawRightString(w - 18 * mm, 8 * mm, f"Página {self._pageNumber} de {total}")
        self.restoreState()


def cover(canvas_obj, doc):
    w, h = A4
    canvas_obj.saveState()
    canvas_obj.setFillColor(NAVY)
    canvas_obj.rect(0, 0, w, h, fill=1, stroke=0)
    canvas_obj.setFillColor(TEAL)
    canvas_obj.rect(0, h - 55 * mm, w, 7 * mm, fill=1, stroke=0)
    canvas_obj.setFillColor(WHITE)
    canvas_obj.setFont(font_bold, 13)
    canvas_obj.drawString(23 * mm, h - 31 * mm, "ULIANA INDÚSTRIA METALÚRGICA LTDA.")
    canvas_obj.setFont(font_bold, 28)
    canvas_obj.drawString(23 * mm, h - 91 * mm, "NF-e Monitor")
    canvas_obj.setFont(font_regular, 16)
    canvas_obj.drawString(23 * mm, h - 105 * mm, "Documentação técnica, funcional e operacional")
    canvas_obj.setFillColor(MINT)
    canvas_obj.roundRect(23 * mm, h - 145 * mm, 164 * mm, 25 * mm, 2 * mm, fill=1, stroke=0)
    canvas_obj.setFillColor(NAVY)
    canvas_obj.setFont(font_bold, 11)
    canvas_obj.drawString(30 * mm, h - 133 * mm, "Finalidade")
    canvas_obj.setFont(font_regular, 9)
    canvas_obj.drawString(30 * mm, h - 140 * mm, "Apoio ao acompanhamento de faturamento, entregas e programa do PCP")
    canvas_obj.setFillColor(WHITE)
    canvas_obj.setFont(font_regular, 10)
    canvas_obj.drawString(23 * mm, 39 * mm, "Versão do documento: 1.0")
    canvas_obj.drawString(23 * mm, 32 * mm, "Data: 29/07/2026")
    canvas_obj.drawString(23 * mm, 25 * mm, "Classificação: uso interno")
    canvas_obj.restoreState()


doc = BaseDocTemplate(
    str(OUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
    topMargin=18 * mm, bottomMargin=18 * mm, title="Documentação NF-e Monitor",
    author="Deivid dos Passos"
)
portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait")
landscape_size = landscape(A4)
landscape_frame = Frame(15 * mm, 16 * mm, landscape_size[0] - 30 * mm, landscape_size[1] - 32 * mm, id="landscape")
doc.addPageTemplates([
    PageTemplate(id="Cover", pagesize=A4, frames=[portrait_frame], onPage=cover),
    PageTemplate(id="Portrait", pagesize=A4, frames=[portrait_frame]),
    PageTemplate(id="Landscape", pagesize=landscape_size, frames=[landscape_frame]),
])

story = [Spacer(1, 245 * mm), NextPageTemplate("Portrait"), PageBreak()]

story += section("Controle do documento", "Registro formal para avaliação, homologação e liberação interna do NF-e Monitor.")
story += [
    data_table([
        ["Campo", "Informação"],
        ["Sistema", "NF-e Monitor – Produtos faturados"],
        ["Empresa", "Uliana Indústria Metalúrgica Ltda."],
        ["Responsável pelo desenvolvimento", "Deivid dos Passos"],
        ["Versão do documento", "1.0"],
        ["Data de emissão", "29/07/2026"],
        ["Ambiente", "Rede local corporativa / Windows"],
        ["Classificação", "Uso interno"],
    ], [55 * mm, 115 * mm], font_size=8.5),
    Spacer(1, 7 * mm),
    P("Histórico de revisão", "H2Local"),
    data_table([
        ["Versão", "Data", "Descrição"],
        ["1.0", "29/07/2026", "Emissão inicial: arquitetura, regras, segurança, operação e evidências."],
    ], [25 * mm, 35 * mm, 110 * mm], font_size=8.3),
    Spacer(1, 7 * mm),
    callout("Objetivo deste documento", "Apresentar o funcionamento integral do sistema, os dados tratados, os controles implementados, os ganhos para o PCP e os cuidados necessários para operação segura na rede interna."),
]

story += [PageBreak()]
story += section("Resumo executivo")
story += [
    P("<b>O NF-e Monitor é uma aplicação local de apoio ao PCP.</b> Ela lê os XMLs de NF-e disponibilizados na pasta corporativa, identifica as vendas aceitas pelas regras fiscais, classifica cada item por montadora e planta e apresenta os resultados em um painel pesquisável."),
    P("A solução reduz o trabalho manual de consultar notas e somar item por item, dia após dia. O analista passa a visualizar o mês corrente consolidado, com número da nota, item, código do cliente, quantidade faturada, programa informado e saldo a entregar."),
    Spacer(1, 3 * mm),
    data_table([
        ["Antes", "Com o NF-e Monitor"],
        ["Extração e conferência diária, repetida por item.", "Índice pronto, com consulta por nota, item, cliente, pedido, data e planta."],
        ["Solicitações mensais exigiam recomposição de vários dias.", "O mês atual é consolidado automaticamente em uma única matriz."],
        ["Maior tempo para responder às montadoras.", "Resposta operacional mais rápida, com rastreabilidade até a NF-e."],
        ["Programa mantido sem controle específico no painel.", "Programa protegido por senha de 6 dígitos por montadora."],
    ], [83 * mm, 87 * mm], font_size=8.1),
    Spacer(1, 6 * mm),
    callout("Princípio de segurança", "O processamento é local. O sistema não envia XMLs ou dados fiscais para serviços em nuvem. A pasta de origem é lida pela rede interna e o índice é gravado em banco SQLite no computador que hospeda o monitor.", BLUE),
]

story += [PageBreak()]
story += section("Escopo funcional")
for item in [
    "<b>Consulta geral:</b> pesquisa em todas as montadoras, inclusive por NF, item, pedido, descrição e código do cliente.",
    "<b>Consulta por montadora e planta:</b> filtros específicos e totais consolidados.",
    "<b>Atualização incremental:</b> processa somente XMLs novos ou alterados.",
    "<b>Atualização automática:</b> varredura em intervalo de 5 minutos.",
    "<b>Atualização manual:</b> o botão Atualizar inicia uma conferência imediata.",
    "<b>Entregas vs Pedido:</b> matriz mensal por item, com quantidades diárias, notas fiscais, faturado, programa e saldo.",
    "<b>Arquivos auxiliares:</b> cancelamentos e cartas de correção são classificados em área separada e não misturados às vendas válidas.",
    "<b>Controle de programa:</b> senha de 6 dígitos por montadora, autorização por sessão e painel administrativo.",
    "<b>Acesso em rede:</b> o painel pode ser consultado por outros computadores da mesma rede enquanto o computador servidor estiver ligado.",
]:
    story.append(bullet(item))
story += [
    Spacer(1, 5 * mm),
    P("Fora do escopo atual", "H2Local"),
    P("O sistema não substitui o ERP/TOTVS, não emite NF-e, não altera XMLs de origem, não executa cancelamentos e não modifica pedidos do cliente. Ele é uma camada local de leitura, consolidação e apoio à decisão."),
]

story += [PageBreak()]
story += section("Arquitetura da solução")
arch = data_table([
    ["Camada", "Componente", "Responsabilidade"],
    ["Origem", r"\\192.168.2.6\erp\SP\nfe", "Repositório corporativo dos XMLs de NF-e, cancelamentos e CC-e."],
    ["Processamento", "Python / server.py", "Varredura, leitura XML, regras fiscais, classificação, APIs e servidor HTTP."],
    ["Persistência", "SQLite / data\\nfe_index.db", "Índice de arquivos, itens aceitos, programas e hashes das senhas."],
    ["Interface", "HTML, CSS e JavaScript", "Dashboard, pesquisa, filtros, matriz PCP e administração."],
    ["Acesso", "HTTP porta 8765", "Uso local ou por endereço IP dentro da rede corporativa."],
], [35 * mm, 55 * mm, 80 * mm], font_size=7.8)
story += [arch, Spacer(1, 8 * mm)]
flow = Table([
    [P("<b>XMLs na rede</b><br/>Somente leitura", "CalloutLocal"),
     P("<b>Indexador</b><br/>Valida e classifica", "CalloutLocal"),
     P("<b>SQLite local</b><br/>Índice e programa", "CalloutLocal"),
     P("<b>Dashboard</b><br/>Consulta e PCP", "CalloutLocal")]
], colWidths=[40 * mm] * 4)
flow.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (0, 0), BLUE),
    ("BACKGROUND", (1, 0), (1, 0), MINT),
    ("BACKGROUND", (2, 0), (2, 0), AMBER),
    ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#E7E9F6")),
    ("BOX", (0, 0), (-1, -1), 0.7, LINE),
    ("INNERGRID", (0, 0), (-1, -1), 0.7, LINE),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 12),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
]))
story += [flow, Spacer(1, 6 * mm), callout("Disponibilidade", "O computador que executa o servidor é o ponto de hospedagem. Para acesso por outros computadores, ele precisa permanecer ligado, conectado à rede e com a porta 8765 liberada no firewall.", LIGHT)]

story += [PageBreak()]
story += section("Tratamento dos XMLs")
story += [
    P("A aplicação percorre os arquivos da pasta configurada, registra tamanho e data de modificação e só reprocessa arquivos novos ou alterados. A leitura usa o parser XML da biblioteca padrão do Python, respeitando namespaces do documento."),
    P("Para cada item aceito, são extraídos, entre outros:", "H2Local"),
    data_table([
        ["Tag XML", "Uso no sistema"],
        ["<nNF> / <nFat>", "Número da nota e número de faturamento."],
        ["<dhEmi>", "Data e hora da emissão."],
        ["<cProd>", "Código interno do item e base de classificação."],
        ["<infAdProd>", "Código do cliente vinculado ao item."],
        ["<xProd>", "Descrição do produto."],
        ["<CFOP>", "Validação da natureza fiscal aceita."],
        ["<qCom>", "Quantidade comercial faturada."],
        ["<xPed>", "Número do pedido do cliente."],
        ["NCM, unidade, valores e GTIN", "Detalhes disponíveis na consulta da nota."],
    ], [45 * mm, 125 * mm], font_size=8.0),
    Spacer(1, 5 * mm),
    P("Regras fiscais aceitas", "H2Local"),
    bullet("<b>5101, 6101 e 7101:</b> CFOPs de venda processados normalmente."),
    bullet("<b>5124:</b> exceção exclusiva para item Honda iniciado por HD, quando a natureza da operação contém industrialização."),
    bullet("Demais CFOPs não alimentam a relação principal de produtos faturados."),
]

story += [PageBreak()]
story += section("Classificação de montadoras e plantas")
story += [
    data_table([
        ["Montadora / planta", "Regra principal"],
        ["Volkswagen · Taubaté", "VK com sufixo T."],
        ["Volkswagen · Curitiba", "VK com sufixo CUR."],
        ["Volkswagen · Anchieta", "VK numérico, exceto regras específicas de São Carlos e MAN."],
        ["Volkswagen · São Carlos", "VK24000 e VK24010."],
        ["Volkswagen · Reposição", "VK com sufixo PA ou REV."],
        ["Volkswagen · MAN", "MN; também VK16000, VK18000, VK20180, VK20210 e VK20100."],
        ["GM · Mogi", "GM com sufixo MC."],
        ["GM · São José dos Campos", "GM com sufixo SJC."],
        ["GM · São Caetano do Sul", "GM numérico, sem sufixo."],
        ["GM · Reposição", "GM com sufixo REV."],
        ["Honda · Paulínia", "HD com sufixo ITP."],
        ["Honda · Reposição", "HD com sufixo PA ou REV."],
    ], [62 * mm, 108 * mm], font_size=7.6),
    Spacer(1, 4 * mm),
    data_table([
        ["Montadora / planta", "Regra principal"],
        ["Scania", "SC sem sufixo especial."],
        ["Scania · Reposição", "SC com sufixo PA ou REV."],
        ["Scania · Exportação", "SC com sufixo E."],
        ["Inalfa", "IA00100, IA00100N, IA00700 e IA00800."],
        ["Prima Soles", "PS00100, PS00110 e PS00200."],
        ["PSA", "PG; sufixos PA/REV são reposição."],
        ["Valeo", "VL00100 e VL00110."],
        ["MWM", "MW13000."],
        ["Reydel", "IB00010."],
    ], [62 * mm, 108 * mm], font_size=7.6),
]

story += [PageBreak(), NextPageTemplate("Landscape")]
story += section("Dashboard de faturamento", "Tela principal com visão consolidada, pesquisa global e rastreabilidade dos itens.")
story += [
    screenshot(TMP / "dashboard_principal.png", "Figura 1 – Dashboard principal do NF-e Monitor.", width=245 * mm),
    PageBreak(),
]

story += section("Entregas vs Pedido", "Matriz mensal criada para acelerar a rotina dos analistas de PCP.")
story += [
    screenshot(TMP / "entregas_pedido.png", "Figura 2 – Visão mensal de entregas, programa e saldo.", width=245 * mm),
    PageBreak(),
]

story += section("Administração de senhas", "Painel lateral exibido somente após autenticação com a credencial administrativa.")
story += [
    screenshot(TMP / "painel_administrativo.png", "Figura 3 – Gestão de senhas de analista por montadora.", width=245 * mm),
    PageBreak(), NextPageTemplate("Portrait"),
]

story += section("Entregas vs Pedido: regras")
story += [
    P("A matriz usa o mês selecionado e agrupa os itens por montadora, planta e produto. Cada coluna diária apresenta a quantidade faturada; ao posicionar o mouse sobre um valor, o usuário consulta as notas que compõem aquele total."),
    data_table([
        ["Coluna", "Origem / comportamento"],
        ["Planta", "Classificação derivada do código do produto."],
        ["Item", "Tag <cProd>."],
        ["Código cliente", "Tag <infAdProd> do item."],
        ["Descrição", "Tag <xProd>."],
        ["Dias 01–31", "Soma das quantidades faturadas no respectivo dia."],
        ["Faturado", "Soma mensal das quantidades aceitas."],
        ["Programa", "Valor manual, persistido no SQLite e protegido por senha."],
        ["Saldo a entregar", "Programa menos Faturado."],
    ], [48 * mm, 122 * mm], font_size=8.1),
    Spacer(1, 6 * mm),
    callout("Responsabilidade operacional", "O valor de Programa deve ser conferido com a informação oficial recebida do cliente. O dashboard calcula o saldo, mas não substitui a validação do analista responsável.", AMBER),
]

story += [PageBreak()]
story += section("Controle de acesso")
story += [
    P("A proteção é aplicada especificamente à coluna Programa, por ser uma informação operacional crítica. Cada montadora possui uma senha de analista com 6 dígitos, válida para todas as suas plantas."),
    data_table([
        ["Controle", "Implementação atual"],
        ["Primeiro uso", "Se não houver senha da montadora, o primeiro PIN válido de 6 dígitos é cadastrado."],
        ["Escopo", "Uma senha por montadora; todas as plantas daquela montadora são liberadas juntas."],
        ["Sessão", "Token aleatório em memória, escopo de montadora e validade de até 8 horas."],
        ["Administrador", "Credencial própria, capaz de autorizar edição e abrir o painel de gestão."],
        ["Armazenamento", "PBKDF2-HMAC-SHA256, 200.000 iterações e salt aleatório de 16 bytes."],
        ["Revogação", "Alterar ou limpar senha revoga tokens de analista relacionados."],
        ["Separação", "Token de analista não acessa as rotas administrativas."],
    ], [45 * mm, 125 * mm], font_size=7.9),
    Spacer(1, 6 * mm),
    callout("Senha administrativa", "A credencial administrativa não é publicada neste documento. Sua guarda e divulgação devem ficar restritas ao responsável designado pela empresa.", LIGHT),
]

story += [PageBreak()]
story += section("Segurança e privacidade")
story += [
    P("<b>Controles existentes</b>", "H2Local"),
    bullet("Processamento realizado no ambiente local, sem integração com nuvem ou envio externo."),
    bullet("Acesso à origem por compartilhamento SMB corporativo."),
    bullet("XMLs de origem são lidos; o sistema não os altera nem os exclui."),
    bullet("Índice e programas armazenados em banco SQLite local."),
    bullet("PINs de analista armazenados como hash com salt, não em texto aberto."),
    bullet("Tokens aleatórios, temporários, mantidos em memória e limitados à montadora."),
    bullet("Arquivos cancelados e cartas de correção ficam separados dos itens válidos."),
    Spacer(1, 4 * mm),
    P("<b>Limites e recomendações</b>", "H2Local"),
    data_table([
        ["Tema", "Situação / recomendação"],
        ["Transporte HTTP", "Não há criptografia TLS. Restringir à LAN confiável e bloquear acesso externo no firewall."],
        ["Credencial ADM", "Centralizar em configuração protegida/variável de ambiente em evolução futura."],
        ["Auditoria", "O sistema não identifica nominalmente o analista. Recomenda-se log de usuário, alteração, data e valor anterior."],
        ["Banco local", "Restringir permissões da pasta data e executar backup periódico."],
        ["Disponibilidade", "Hospedar em computador estável, com energia e rede monitoradas."],
        ["Permissões SMB", "Conceder somente os acessos necessários; preferir leitura para a conta do monitor."],
    ], [38 * mm, 132 * mm], font_size=7.7),
]

story += [PageBreak()]
story += section("Operação do sistema")
story += [
    P("Inicialização", "H2Local"),
    bullet("Executar <b>iniciar.bat</b> no computador servidor."),
    bullet("Acessar <b>http://localhost:8765</b> no próprio computador."),
    bullet("Nos demais computadores, usar <b>http://IP-DO-SERVIDOR:8765</b>."),
    bullet("Na primeira configuração de rede, executar <b>liberar_acesso_rede.bat</b> como administrador."),
    P("Atualização", "H2Local"),
    bullet("O monitor verifica novos XMLs automaticamente a cada 5 minutos."),
    bullet("O botão Atualizar executa uma verificação imediata."),
    bullet("A atualização é incremental: arquivos sem alteração não são novamente analisados."),
    P("Encerramento", "H2Local"),
    bullet("Fechar a janela do servidor interrompe o acesso de todos os computadores."),
    bullet("O banco permanece salvo e será reutilizado na próxima inicialização."),
    Spacer(1, 5 * mm),
    callout("Tempo de aparecimento de uma nota", "Em condição normal, uma nota nova aparece na próxima varredura, em até aproximadamente 5 minutos. O tempo pode aumentar se o XML ainda não estiver disponível na pasta de rede ou se houver indisponibilidade do compartilhamento.", BLUE),
]

story += [PageBreak()]
story += section("Manutenção, backup e recuperação")
story += [
    data_table([
        ["Atividade", "Orientação"],
        ["Backup principal", r"Copiar data\nfe_index.db com o servidor parado."],
        ["Arquivos auxiliares SQLite", "Se existirem .db-wal e .db-shm, incluir no backup ou parar o servidor antes da cópia."],
        ["Restaurar", "Com o servidor parado, repor o banco validado na pasta data."],
        ["Reconstruir índice", "Em caso de perda do banco, uma nova inicialização recompõe o índice a partir dos XMLs; os Programas manuais precisam de backup."],
        ["Alterar regras", "Modificar classify_product e regras fiscais em server.py, seguido de teste de regressão."],
        ["Monitorar", "Conferir status, última atualização, erros e acesso ao compartilhamento."],
    ], [45 * mm, 125 * mm], font_size=7.9),
    Spacer(1, 6 * mm),
    P("Estrutura de arquivos", "H2Local"),
    data_table([
        ["Caminho", "Finalidade"],
        ["server.py", "Servidor HTTP, indexação, regras e APIs."],
        ["static/index.html", "Estrutura da interface."],
        ["static/styles.css", "Identidade visual e responsividade."],
        ["static/app.js", "Navegação, consultas, filtros e autenticação."],
        ["assets/", "Logotipos das montadoras."],
        ["data/nfe_index.db", "Banco local do sistema."],
        ["iniciar.bat", "Inicialização simplificada."],
        ["liberar_acesso_rede.bat", "Regra de firewall e orientação de IP."],
    ], [55 * mm, 115 * mm], font_size=8.0),
]

story += [PageBreak()]
story += section("Modelo de dados")
story += [
    data_table([
        ["Tabela", "Conteúdo", "Observação"],
        ["files", "Caminho, tamanho, modificação, status e erro.", "Controla processamento incremental e categorias."],
        ["items", "NF, data, item, cliente, CFOP, quantidade, pedido, montadora e planta.", "Base das consultas e totais."],
        ["delivery_programs", "Mês, montadora, planta, item e quantidade programada.", "Entrada manual do PCP."],
        ["security_settings", "Hash da senha por montadora e atualização.", "Não armazena PIN de analista legível."],
    ], [38 * mm, 73 * mm, 59 * mm], font_size=7.8),
    Spacer(1, 7 * mm),
    P("APIs locais", "H2Local"),
    data_table([
        ["Rota", "Método", "Finalidade"],
        ["/api/status", "GET", "Estado da indexação e contagens."],
        ["/api/items", "GET", "Consulta paginada de itens faturados."],
        ["/api/files", "GET", "Cancelamentos e cartas de correção."],
        ["/api/deliveries", "GET", "Matriz mensal do PCP."],
        ["/api/refresh", "POST", "Atualização manual."],
        ["/api/program-auth", "POST", "Autorização por montadora."],
        ["/api/delivery-program", "POST", "Gravação do Programa autorizado."],
        ["/api/admin-passwords", "POST", "Lista, troca e limpeza administrativa."],
    ], [60 * mm, 22 * mm, 88 * mm], font_size=7.8),
]

story += [PageBreak()]
story += section("Validação e critérios de aceite")
story += [
    P("Os testes realizados nesta versão confirmaram:", "H2Local"),
    bullet("Sintaxe válida do servidor Python e do JavaScript da interface."),
    bullet("Autorização ADM e abertura do painel lateral de administração."),
    bullet("Listagem de montadoras e estado de senha cadastrada."),
    bullet("Troca de senha por montadora e rejeição da senha anterior."),
    bullet("Bloqueio da rota administrativa para token de analista."),
    bullet("Limpeza individual e limpeza geral das senhas."),
    bullet("Revogação das autorizações de analista após alteração ou limpeza."),
    bullet("Carregamento real do dashboard, da matriz Entregas vs Pedido e dos dados indexados."),
    Spacer(1, 6 * mm),
    data_table([
        ["Critério para homologação", "Resultado esperado"],
        ["Origem acessível", "Compartilhamento disponível com a conta que executa o serviço."],
        ["Nota nova", "Aparece em até 5 minutos ou após atualização manual."],
        ["Classificação", "Item exibido na montadora e planta corretas."],
        ["Cancelados / CC-e", "Não aparecem misturados aos produtos faturados."],
        ["Programa", "Só pode ser alterado após autenticação da montadora ou ADM."],
        ["Rede", "Acesso permitido apenas aos computadores autorizados da LAN."],
    ], [60 * mm, 110 * mm], font_size=8.0),
]

story += [PageBreak()]
story += section("Riscos e plano de evolução")
story += [
    data_table([
        ["Prioridade", "Evolução recomendada", "Benefício"],
        ["Alta", "Mover a credencial ADM para variável de ambiente ou cofre local.", "Reduz exposição no código-fonte."],
        ["Alta", "Criar trilha de auditoria nominal das alterações de Programa.", "Responsabilização e rastreabilidade."],
        ["Alta", "Definir rotina de backup do SQLite e teste de restauração.", "Proteção dos Programas manuais."],
        ["Média", "Executar como serviço do Windows com reinício automático.", "Maior disponibilidade."],
        ["Média", "Adicionar autenticação de usuário integrada à rede corporativa.", "Controle individual de acesso."],
        ["Média", "Publicar com HTTPS interno, se o alcance de rede aumentar.", "Proteção do tráfego em trânsito."],
        ["Baixa", "Painel de saúde e alertas para falha no compartilhamento.", "Detecção mais rápida de indisponibilidade."],
    ], [23 * mm, 94 * mm, 53 * mm], font_size=7.5),
    Spacer(1, 7 * mm),
    callout("Conclusão de segurança", "Para o escopo atual, o sistema mantém o processamento e a persistência no ambiente local e aplica proteção específica à informação de Programa. A liberação deve ser acompanhada de restrição de rede, controle da credencial administrativa e rotina de backup.", MINT),
]

story += [PageBreak()]
story += section("Conclusão")
story += [
    P("O NF-e Monitor transforma XMLs já disponíveis no ambiente corporativo em informação operacional estruturada. Sua principal contribuição é reduzir o tempo gasto pelos analistas de PCP para levantar o que foi faturado e entregue, principalmente em solicitações que abrangem o mês inteiro."),
    P("A solução oferece pesquisa consolidada, classificação por montadora e planta, visão mensal por item e controle do Programa por senha. O projeto não interfere no ERP e não altera a documentação fiscal de origem."),
    Spacer(1, 8 * mm),
    callout("Parecer para avaliação interna", "O sistema está tecnicamente apto para homologação controlada na rede local, desde que sejam mantidos os controles de acesso à pasta XML, firewall restrito à LAN, guarda da credencial administrativa e backup periódico do banco local.", BLUE),
    Spacer(1, 16 * mm),
    HRFlowable(width="70%", thickness=0.7, color=LINE),
    Spacer(1, 3 * mm),
    P("<b>Desenvolvido por Deivid dos Passos</b>", "CaptionLocal"),
]

doc.build(story, canvasmaker=NumberedCanvas)
print(OUT)
