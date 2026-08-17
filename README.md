# Monitor NF-e - Montadoras

Sistema local para indexar XMLs em:

`\\192.168.2.6\erp\SP\nfe`

## Regras atuais

- Processa vendas com `CFOP = 5101`, `6101` e `7101`.
- Processa itens `UC` da Uliana Componentes com `CFOP = 6101`, `6102` e
  `6103`.
- Processa `CFOP = 5124` somente para itens Honda iniciados em `HD`
  com natureza de industrializacao.
- Volkswagen Taubate: codigo `VK` terminado em `T`.
- Volkswagen Anchieta: codigo `VK` seguido apenas por numeros.
- Volkswagen Curitiba: codigo `VK` terminado em `CUR`.
- Uliana Componentes: codigo iniciado em `UC`; itens terminados em `PA` sao
  classificados como `Reposicao`.
- Outros codigos `VK` ficam em `Revisar`.
- Scania, GM, Honda e Inalfa estao preparadas na interface para as proximas regras.

## Execucao

Abra `iniciar.bat` ou execute:

```powershell
python server.py
```

Acesse `http://localhost:8765`.

O primeiro processamento cria `data/nfe_index.db`. Nas atualizacoes seguintes,
somente arquivos novos ou alterados sao lidos novamente.

O indice verifica novos XMLs automaticamente a cada 5 minutos. O botao
`Atualizar` executa uma verificacao imediata.

## Conferencia da sequencia de NF-e

- O monitor confere a sequencia dos arquivos `01001NNNNNNN.xml` considerando
  somente o ultimo ano pela data real de emissao `dhEmi`.
- Cancelamentos (`_Cancel.xml`) e inutilizacoes (`_Inut.xml`) nao sao apontados
  como lacunas. Cartas de correcao tambem nao substituem o XML normal da NF-e.
- Notas sem XML aparecem em um aviso vermelho no dashboard.
- Se `DATASUL Interactive` estiver aberto no computador servidor, o monitor usa
  o programa `SPFT046`, estabelecimento `01` e serie `1` para solicitar os XMLs.
- Numeros consecutivos sao enviados como uma unica faixa. Cada lacuna e tentada
  uma vez automaticamente; o botao `Recuperar no Datasul` permite nova tentativa.
- A recuperacao automatica e bloqueada se forem detectadas mais de 100 lacunas
  em um ciclo, evitando comandos em massa diante de uma sequencia anormal.

## Protecao do Programa

- A coluna `Programa` e protegida por montadora.
- No primeiro uso de cada montadora, uma senha de analista com 6 digitos e
  cadastrada.
- Apos autorizar uma montadora, todas as plantas e itens dela ficam liberados
  durante a sessao atual.
- Cada montadora possui sua propria senha.
- Depois do cadastro, somente a senha da montadora ou a senha administrativa
  autorizam.
- A senha administrativa nao altera nem cadastra o PIN de analista.
- Ao autorizar com a credencial administrativa, o sistema abre o painel
  `Senhas por montadora`.
- Nesse painel, o administrador pode selecionar a montadora, alterar ou limpar
  sua senha de analista e limpar todas as senhas cadastradas.
- Alterar ou limpar uma senha revoga as autorizacoes de analista relacionadas.
- O PIN e armazenado como hash com salt, nunca em texto aberto.

## Acesso pela rede local

Ao iniciar o sistema, consulte a linha `Acesso na rede` exibida na janela.
Em outro computador, abra exatamente esse endereco.

Na primeira configuracao, execute `liberar_acesso_rede.bat` uma vez e confirme
a solicitacao de administrador do Windows.

O computador que executa `iniciar.bat` precisa permanecer ligado e com o sistema
em execucao.
